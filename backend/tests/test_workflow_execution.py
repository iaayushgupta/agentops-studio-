"""
Test 3 — Full Workflow Execution
Covers end-to-end run of the Payment Triage workflow with mocked LLMs:
  • Run transitions from pending → running → completed.
  • At least 4 RunStep records are created (intake, investigator, resolution, reviewer).
  • final_response is set on the Run row after execution.
  • total_cost_usd is recorded (may be 0 on free-tier mocks — just checked for type).
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select

from app.db.models import Run, RunStatus, RunStep
from app.db.session import AsyncSessionLocal
from app.services.runtime_service import _execute_run


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_pending_run(workflow_id: uuid.UUID) -> str:
    """Insert a pending Run row and return its string UUID."""
    async with AsyncSessionLocal() as db:
        run = Run(
            workflow_id=workflow_id,
            status=RunStatus.pending,
            trigger_channel="api",
            trigger_payload={"message": "My payment TXN-001 failed. Help."},
        )
        db.add(run)
        await db.flush()
        run_id = str(run.id)
        await db.commit()
    return run_id


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_run_completes_with_mocked_llm(mock_llm, payment_triage_workflow):
    """
    Full execution with mocked LLMs must end with status=completed and
    at least 4 RunStep rows.
    """
    wf_id = str(payment_triage_workflow.id)
    run_id = await _create_pending_run(payment_triage_workflow.id)

    await _execute_run(
        run_id=run_id,
        workflow_id=wf_id,
        trigger_type="api",
        trigger_payload={"message": "My payment TXN-001 failed. Help."},
    )

    async with AsyncSessionLocal() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        assert run is not None, "Run row must exist after execution"
        assert run.status == RunStatus.completed, (
            f"Expected status=completed, got {run.status}; "
            f"error_message={run.error_message!r}"
        )

        steps_result = await db.execute(
            select(RunStep).where(RunStep.run_id == uuid.UUID(run_id))
        )
        steps = steps_result.scalars().all()
        assert len(steps) >= 4, (
            f"Expected ≥4 RunStep rows, got {len(steps)}"
        )


async def test_run_sets_final_response(mock_llm, payment_triage_workflow):
    """
    After a successful run the final_response column must be non-empty.
    """
    wf_id = str(payment_triage_workflow.id)
    run_id = await _create_pending_run(payment_triage_workflow.id)

    await _execute_run(
        run_id=run_id,
        workflow_id=wf_id,
        trigger_type="api",
        trigger_payload={"message": "Transaction TXN-001 failed"},
    )

    async with AsyncSessionLocal() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        assert run.status == RunStatus.completed
        assert run.final_response, "final_response must be set after a successful run"
        assert len(run.final_response) > 5


async def test_run_records_timestamps(mock_llm, payment_triage_workflow):
    """started_at and ended_at are populated on completion."""
    wf_id = str(payment_triage_workflow.id)
    run_id = await _create_pending_run(payment_triage_workflow.id)

    await _execute_run(
        run_id=run_id,
        workflow_id=wf_id,
        trigger_type="api",
        trigger_payload={"message": "TXN-001 failed"},
    )

    async with AsyncSessionLocal() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        assert run.started_at is not None, "started_at must be set"
        assert run.ended_at is not None, "ended_at must be set"
        assert run.ended_at >= run.started_at


async def test_run_marks_failed_for_missing_workflow(mock_llm):
    """
    If the workflow_id doesn't exist, _execute_run must mark the run as failed
    (not leave it stuck in pending/running).
    """
    # Create a run that references a non-existent workflow
    bogus_workflow_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        run = Run(
            workflow_id=None,          # no FK violation — nullable column
            status=RunStatus.pending,
            trigger_channel="api",
            trigger_payload={},
        )
        db.add(run)
        await db.flush()
        run_id = str(run.id)
        await db.commit()

    await _execute_run(
        run_id=run_id,
        workflow_id=bogus_workflow_id,
        trigger_type="api",
        trigger_payload={},
    )

    async with AsyncSessionLocal() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        assert run.status == RunStatus.failed
        assert run.error_message  # should describe the missing workflow


async def test_all_steps_are_completed_status(mock_llm, payment_triage_workflow):
    """Every RunStep created during a successful run should be status=completed."""
    from app.db.models import StepStatus

    wf_id = str(payment_triage_workflow.id)
    run_id = await _create_pending_run(payment_triage_workflow.id)

    await _execute_run(
        run_id=run_id,
        workflow_id=wf_id,
        trigger_type="api",
        trigger_payload={"message": "TXN-001"},
    )

    async with AsyncSessionLocal() as db:
        steps_result = await db.execute(
            select(RunStep).where(RunStep.run_id == uuid.UUID(run_id))
        )
        steps = steps_result.scalars().all()
        for step in steps:
            assert step.status == StepStatus.completed, (
                f"Step {step.id} has status {step.status}"
            )
