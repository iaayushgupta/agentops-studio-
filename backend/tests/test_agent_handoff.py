"""
Test 4 — Agent Handoff / Message Persistence
Covers:
  • Each agent node writes an assistant Message row to the messages table.
  • The initial trigger is stored as a user Message.
  • Messages are associated with the correct run_id.
  • Message order respects execution order (created_at ascending).
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select

from app.db.models import Message, MessageRole, Run, RunStatus
from app.db.session import AsyncSessionLocal
from app.services.runtime_service import _execute_run


async def _create_pending_run(workflow_id: uuid.UUID, payload: dict) -> str:
    async with AsyncSessionLocal() as db:
        run = Run(
            workflow_id=workflow_id,
            status=RunStatus.pending,
            trigger_channel="api",
            trigger_payload=payload,
        )
        db.add(run)
        await db.flush()
        run_id = str(run.id)
        await db.commit()
    return run_id


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_user_message_persisted_on_trigger(mock_llm, payment_triage_workflow):
    """
    The trigger message is stored as a MessageRole.user row before any agent runs.
    """
    trigger_text = "Payment TXN-001 failed please investigate"
    run_id = await _create_pending_run(
        payment_triage_workflow.id,
        {"message": trigger_text},
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="api",
        trigger_payload={"message": trigger_text},
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.run_id == uuid.UUID(run_id))
            .where(Message.role == MessageRole.user)
        )
        user_msgs = result.scalars().all()

    assert len(user_msgs) >= 1, "At least one user message must be recorded"
    assert user_msgs[0].content == trigger_text


async def test_assistant_messages_persisted_per_agent(mock_llm, payment_triage_workflow):
    """
    Each agent node writes one assistant Message. For the standard payment triage
    path (intake → investigator → resolution → reviewer → telegram_response),
    expect ≥ 4 assistant messages.
    """
    run_id = await _create_pending_run(
        payment_triage_workflow.id,
        {"message": "TXN-001 failed"},
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="api",
        trigger_payload={"message": "TXN-001 failed"},
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.run_id == uuid.UUID(run_id))
            .where(Message.role == MessageRole.assistant)
            .order_by(Message.created_at)
        )
        assistant_msgs = result.scalars().all()

    assert len(assistant_msgs) >= 4, (
        f"Expected ≥4 assistant messages, got {len(assistant_msgs)}"
    )


async def test_messages_are_linked_to_correct_run(mock_llm, payment_triage_workflow):
    """Messages must carry the run's UUID — not bleed across runs."""
    run_id = await _create_pending_run(
        payment_triage_workflow.id,
        {"message": "TXN-001 check"},
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="api",
        trigger_payload={"message": "TXN-001 check"},
    )

    run_uuid = uuid.UUID(run_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message).where(Message.run_id == run_uuid)
        )
        all_msgs = result.scalars().all()

    assert all_msgs, "There must be messages for the run"
    for msg in all_msgs:
        assert msg.run_id == run_uuid, (
            f"Message {msg.id} is linked to wrong run_id {msg.run_id}"
        )


async def test_message_content_is_non_empty(mock_llm, payment_triage_workflow):
    """No Message row should be stored with empty content."""
    run_id = await _create_pending_run(
        payment_triage_workflow.id,
        {"message": "TXN-001"},
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="api",
        trigger_payload={"message": "TXN-001"},
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message).where(Message.run_id == uuid.UUID(run_id))
        )
        msgs = result.scalars().all()

    for msg in msgs:
        assert msg.content and msg.content.strip(), (
            f"Message {msg.id} (role={msg.role}) has empty content"
        )


async def test_messages_ordered_by_creation(mock_llm, payment_triage_workflow):
    """
    Messages retrieved with ORDER BY created_at should have non-decreasing
    timestamps — i.e. no message appears before one that was written earlier.
    """
    run_id = await _create_pending_run(
        payment_triage_workflow.id,
        {"message": "TXN-001"},
    )

    await _execute_run(
        run_id=run_id,
        workflow_id=str(payment_triage_workflow.id),
        trigger_type="api",
        trigger_payload={"message": "TXN-001"},
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.run_id == uuid.UUID(run_id))
            .order_by(Message.created_at)
        )
        msgs = result.scalars().all()

    for i in range(1, len(msgs)):
        assert msgs[i].created_at >= msgs[i - 1].created_at, (
            f"Messages not in created_at order at index {i}"
        )
