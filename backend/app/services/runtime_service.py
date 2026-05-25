"""RuntimeService — creates runs, fires background execution, returns timelines."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Message, MessageRole, Run, RunStatus, RunStep,
    ToolCall, TokenUsage, Workflow,
)
from app.db.session import AsyncSessionLocal
from app.services.observability_service import (
    EVT_RUN_COMPLETED, EVT_RUN_FAILED, EVT_RUN_STARTED,
    ObservabilityService,
)

logger = logging.getLogger(__name__)


class RuntimeService:
    """
    Thin service layer between the HTTP API and the LangGraph runtime.

    trigger_run  — creates a Run row and fires a background asyncio task (NON-BLOCKING).
    get_run_timeline — returns the full audit trail for a run.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Public: trigger (non-blocking) ────────────────────────────────────────

    async def trigger_run(
        self,
        workflow_id: uuid.UUID,
        trigger_channel: str | None = "api",
        trigger_payload: dict | None = None,
    ) -> Run:
        """
        Create a Run record with status='pending' and schedule execution
        as an asyncio background task.  Returns the Run immediately.
        """
        payload = trigger_payload or {}
        run = Run(
            workflow_id=workflow_id,
            status=RunStatus.pending,
            trigger_channel=trigger_channel,
            trigger_payload=payload,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)

        run_id = str(run.id)
        wf_id = str(workflow_id)
        asyncio.create_task(
            _execute_run(run_id, wf_id, trigger_channel or "api", payload),
            name=f"run-{run_id}",
        )
        logger.info("Run %s queued for workflow %s (channel=%s)", run_id, wf_id, trigger_channel)
        return run

    # ── Public: timeline ──────────────────────────────────────────────────────

    async def get_run_timeline(self, run_id: uuid.UUID) -> dict:
        """
        Return the full audit trail for a run:
          { run, steps, messages, tool_calls }
        All collections are ordered by created_at / started_at.
        """
        run_result = await self.db.execute(select(Run).where(Run.id == run_id))
        run = run_result.scalar_one_or_none()
        if run is None:
            return {}

        steps_result = await self.db.execute(
            select(RunStep)
            .where(RunStep.run_id == run_id)
            .order_by(RunStep.started_at)
        )
        steps = steps_result.scalars().all()

        msgs_result = await self.db.execute(
            select(Message)
            .where(Message.run_id == run_id)
            .order_by(Message.created_at)
        )
        messages = msgs_result.scalars().all()

        step_ids = [s.id for s in steps]
        tool_calls: list[ToolCall] = []
        if step_ids:
            tc_result = await self.db.execute(
                select(ToolCall)
                .where(ToolCall.run_step_id.in_(step_ids))
                .order_by(ToolCall.created_at)
            )
            tool_calls = tc_result.scalars().all()

        token_result = await self.db.execute(
            select(
                sqlfunc.sum(TokenUsage.prompt_tokens),
                sqlfunc.sum(TokenUsage.completion_tokens),
                sqlfunc.sum(TokenUsage.total_tokens),
                sqlfunc.sum(TokenUsage.estimated_cost),
            ).where(TokenUsage.run_id == run_id)
        )
        tok = token_result.one()

        return {
            "run": {
                "id": str(run.id),
                "workflow_id": str(run.workflow_id) if run.workflow_id else None,
                "status": run.status.value,
                "trigger_channel": run.trigger_channel,
                "trigger_payload": run.trigger_payload,
                "error_message": run.error_message,
                "total_cost_usd": run.total_cost_usd,
                "final_response": run.final_response,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                "created_at": run.created_at.isoformat(),
            },
            "steps": [
                {
                    "id": str(s.id),
                    "agent_id": str(s.agent_id) if s.agent_id else None,
                    "status": s.status.value,
                    "input": s.input,
                    "output": s.output,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                }
                for s in steps
            ],
            "messages": [
                {
                    "id": str(m.id),
                    "role": m.role.value,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
            "tool_calls": [
                {
                    "id": str(tc.id),
                    "tool_name": tc.tool_name,
                    "input": tc.input,
                    "output": tc.output,
                    "created_at": tc.created_at.isoformat(),
                }
                for tc in tool_calls
            ],
            "token_usage": {
                "prompt_tokens": tok[0] or 0,
                "completion_tokens": tok[1] or 0,
                "total_tokens": tok[2] or 0,
                "estimated_cost_usd": float(tok[3] or 0.0),
            },
        }


# ── Background task (module-level, runs outside request context) ───────────────

async def _execute_run(
    run_id: str,
    workflow_id: str,
    trigger_type: str,
    trigger_payload: dict,
) -> None:
    """
    Background asyncio task that drives the full LangGraph execution:
    1. Set run status → running
    2. Fetch workflow + compile graph
    3. Build initial WorkflowState
    4. ainvoke the compiled graph
    5. Mark run completed (or failed on any exception)
    6. Send Telegram response if triggered from Telegram
    """
    obs = ObservabilityService()

    # ── Step 1: mark running ──────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        run = await db.get(Run, uuid.UUID(run_id))
        if run is None:
            logger.error("_execute_run: run %s not found", run_id)
            return
        run.status = RunStatus.running
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

    await obs.broadcast(run_id, EVT_RUN_STARTED, {"workflow_id": workflow_id})

    try:
        # ── Step 2: fetch workflow + compile ──────────────────────────────────
        async with AsyncSessionLocal() as db:
            workflow = await db.get(Workflow, uuid.UUID(workflow_id))
            if workflow is None:
                raise ValueError(f"Workflow {workflow_id} not found")

        from app.runtime.compiler import WorkflowCompiler, WorkflowState

        compiler = WorkflowCompiler()
        compiled = await compiler.compile(workflow)

        # ── Step 3: persist the trigger message ──────────────────────────────
        user_text: str = (
            trigger_payload.get("text")
            or trigger_payload.get("message")
            or str(trigger_payload)
        )

        async with AsyncSessionLocal() as db:
            await obs.record_message(
                db, run_id, MessageRole.user, user_text
            )
            await db.commit()

        # ── Step 4: build initial state ───────────────────────────────────────
        initial_state: WorkflowState = {
            "run_id": run_id,
            "messages": [HumanMessage(content=user_text)],
            "current_output": {},
            "iteration_count": 0,
            "reviewer_score": None,
            "failure_type": None,
            "final_response": None,
            "trigger_payload": trigger_payload,
            "total_cost_usd": 0.0,
        }

        # ── Step 5: invoke graph ──────────────────────────────────────────────
        config = {"configurable": {"thread_id": run_id}}
        final_state: dict = await compiled.ainvoke(initial_state, config=config)

        # ── Step 6: compute total cost (sum estimated_cost from token_usage) ────
        async with AsyncSessionLocal() as db:
            tok_result = await db.execute(
                select(
                    sqlfunc.sum(TokenUsage.total_tokens),
                    sqlfunc.sum(TokenUsage.estimated_cost),  # BUG 3 fix
                ).where(TokenUsage.run_id == uuid.UUID(run_id))
            )
            row = tok_result.one()
            total_tokens = row[0] or 0
            total_cost = float(row[1] or 0.0)  # BUG 3 fix: real cost from MODEL_PRICES

            run = await db.get(Run, uuid.UUID(run_id))
            run.status = RunStatus.completed
            run.ended_at = datetime.now(timezone.utc)
            run.total_cost_usd = total_cost
            await db.commit()

        await obs.broadcast(run_id, EVT_RUN_COMPLETED, {
            "final_response": final_state.get("final_response"),
            "total_tokens": total_tokens,
        })

        # ── Step 7: send Telegram reply if needed ─────────────────────────────
        final_text = final_state.get("final_response")
        if trigger_type == "telegram" and final_text:
            chat_id = trigger_payload.get("sender") or trigger_payload.get("chat_id")
            if chat_id:
                try:
                    from app.channels.telegram.handler import send_response
                    await send_response(chat_id, final_text)
                except Exception as tg_exc:
                    logger.warning("Failed to send Telegram reply: %s", tg_exc)

        logger.info("Run %s completed", run_id)

    except Exception as exc:
        logger.error("Run %s failed: %s", run_id, exc, exc_info=True)

        async with AsyncSessionLocal() as db:
            run = await db.get(Run, uuid.UUID(run_id))
            if run:
                run.status = RunStatus.failed
                run.ended_at = datetime.now(timezone.utc)
                run.error_message = str(exc)
                await db.commit()

        await obs.broadcast(run_id, EVT_RUN_FAILED, {"error": str(exc)})
