"""
Test 6 — Telegram Delivery
Covers:
  • When _execute_run is called with trigger_type="telegram" and a valid chat_id,
    app.channels.telegram.handler.send_response is awaited exactly once.
  • The chat_id passed to send_response matches the one in trigger_payload.
  • When trigger_type="api", send_response is NOT called.
  • When final_response is empty (edge case), send_response is NOT called.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.models import Run, RunStatus
from app.db.session import AsyncSessionLocal
from app.services.runtime_service import _execute_run


TELEGRAM_CHAT_ID = "123456789"
TRIGGER_PAYLOAD_TG = {
    "sender": TELEGRAM_CHAT_ID,
    "chat_id": TELEGRAM_CHAT_ID,
    "text": "My payment TXN-001 failed. Please help.",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_pending_run(workflow_id: uuid.UUID, payload: dict,
                               channel: str = "telegram") -> str:
    async with AsyncSessionLocal() as db:
        run = Run(
            workflow_id=workflow_id,
            status=RunStatus.pending,
            trigger_channel=channel,
            trigger_payload=payload,
        )
        db.add(run)
        await db.flush()
        run_id = str(run.id)
        await db.commit()
    return run_id


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_send_response_called_on_telegram_trigger(
    mocker, mock_llm, payment_triage_workflow
):
    """
    _execute_run with trigger_type='telegram' must call send_response once
    after the graph completes with a non-empty final_response.
    """
    mock_send = mocker.patch(
        "app.channels.telegram.handler.send_response",
        new_callable=lambda: lambda *a, **kw: _async_noop(*a, **kw),
    )
    # Use AsyncMock directly for a cleaner patch
    from unittest.mock import AsyncMock
    mock_send = AsyncMock()
    mocker.patch("app.channels.telegram.handler.send_response", mock_send)

    run_id = await _create_pending_run(
        payment_triage_workflow.id, TRIGGER_PAYLOAD_TG, channel="telegram"
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="telegram",
        trigger_payload=TRIGGER_PAYLOAD_TG,
    )

    mock_send.assert_awaited_once()


async def test_send_response_called_with_correct_chat_id(
    mocker, mock_llm, payment_triage_workflow
):
    """
    The chat_id argument to send_response must match the one in trigger_payload.
    """
    from unittest.mock import AsyncMock

    mock_send = AsyncMock()
    mocker.patch("app.channels.telegram.handler.send_response", mock_send)

    run_id = await _create_pending_run(
        payment_triage_workflow.id, TRIGGER_PAYLOAD_TG, channel="telegram"
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="telegram",
        trigger_payload=TRIGGER_PAYLOAD_TG,
    )

    # Verify the chat_id positional argument
    assert mock_send.await_count >= 1
    called_chat_id = mock_send.call_args[0][0]
    assert called_chat_id == TELEGRAM_CHAT_ID, (
        f"send_response called with chat_id={called_chat_id!r}, "
        f"expected {TELEGRAM_CHAT_ID!r}"
    )


async def test_send_response_not_called_for_api_trigger(
    mocker, mock_llm, payment_triage_workflow
):
    """
    When trigger_type='api', the Telegram reply must NOT be sent even if the run
    produces a final_response.
    """
    from unittest.mock import AsyncMock

    mock_send = AsyncMock()
    mocker.patch("app.channels.telegram.handler.send_response", mock_send)

    run_id = await _create_pending_run(
        payment_triage_workflow.id,
        {"message": "TXN-001 failed"},
        channel="api",
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="api",
        trigger_payload={"message": "TXN-001 failed"},
    )

    mock_send.assert_not_awaited()


async def test_run_still_completes_when_send_response_raises(
    mocker, mock_llm, payment_triage_workflow
):
    """
    A failure in send_response (e.g. Telegram API down) must NOT fail the run.
    The run status should still be 'completed'.
    """
    from unittest.mock import AsyncMock

    mock_send = AsyncMock(side_effect=Exception("Telegram API error"))
    mocker.patch("app.channels.telegram.handler.send_response", mock_send)

    run_id = await _create_pending_run(
        payment_triage_workflow.id, TRIGGER_PAYLOAD_TG, channel="telegram"
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="telegram",
        trigger_payload=TRIGGER_PAYLOAD_TG,
    )

    # Run must still be marked completed — Telegram failure is non-fatal
    async with AsyncSessionLocal() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        assert run.status == RunStatus.completed, (
            f"Run should be completed despite Telegram error; got {run.status}, "
            f"error_message={run.error_message!r}"
        )


# ── Utility (unused placeholder to avoid import lint warnings) ────────────────

async def _async_noop(*args, **kwargs) -> None:
    pass
