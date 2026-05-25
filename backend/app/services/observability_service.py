"""ObservabilityService — singleton for WebSocket broadcasting + DB telemetry writes."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TokenUsage, ToolCall, MessageRole, Message

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── Model pricing (USD per 1M tokens) — BUG 3 fix ────────────────────────────
# Prices as of 2026-05 for the two free-tier providers used in this project.
# input  = prompt token price per 1M
# output = completion token price per 1M
MODEL_PRICES: dict[str, dict[str, float]] = {
    "gemini-1.5-flash":            {"input": 0.075,  "output": 0.30},
    "gemini-1.5-flash-latest":     {"input": 0.075,  "output": 0.30},
    "gemini-1.5-pro":              {"input": 3.50,   "output": 10.50},
    "llama-3.3-70b-versatile":     {"input": 0.59,   "output": 0.79},
    "llama-3.1-8b-instant":        {"input": 0.05,   "output": 0.08},
}


def _compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for a single LLM call given token counts."""
    prices = MODEL_PRICES.get(model) or MODEL_PRICES.get(model.split("/")[-1]) or {}
    input_price = prices.get("input", 0.0)
    output_price = prices.get("output", 0.0)
    return (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price


# ── Event type constants ───────────────────────────────────────────────────────
EVT_RUN_STARTED = "run_started"
EVT_STEP_STARTED = "step_started"
EVT_STEP_COMPLETED = "step_completed"
EVT_TOOL_CALLED = "tool_called"
EVT_MESSAGE_CREATED = "message_created"
EVT_RUN_COMPLETED = "run_completed"
EVT_RUN_FAILED = "run_failed"
EVT_GUARDRAIL_VIOLATED = "guardrail_violated"


class ObservabilityService:
    """
    Singleton service.  Two responsibilities:

    1. WebSocket pub/sub
       register(run_id, ws)  → subscribe a WebSocket to a run's event stream
       unregister(run_id, ws)→ remove subscription (called on disconnect)
       broadcast(run_id, event_type, data) → push to all subscribers

    2. DB persistence helpers (called from compiler node closures)
       record_token_usage(db, run_id, ...)  → writes token_usage row
       record_tool_call(db, step_id, ...)   → writes tool_calls row
       record_message(db, run_id, role, content) → writes messages row
    """

    _instance: ObservabilityService | None = None

    # ── Singleton ──────────────────────────────────────────────────────────────

    def __new__(cls) -> ObservabilityService:
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._sockets: dict[str, list[WebSocket]] = {}
            cls._instance = inst
        return cls._instance

    # ── WebSocket registry ─────────────────────────────────────────────────────

    def register(self, run_id: str, ws: WebSocket) -> None:
        self._sockets.setdefault(run_id, []).append(ws)
        logger.debug("WS registered for run %s (%d total)", run_id, len(self._sockets[run_id]))

    def unregister(self, run_id: str, ws: WebSocket) -> None:
        sockets = self._sockets.get(run_id, [])
        try:
            sockets.remove(ws)
        except ValueError:
            pass
        logger.debug("WS unregistered for run %s", run_id)

    # ── Broadcasting ───────────────────────────────────────────────────────────

    async def broadcast(self, run_id: str, event_type: str, data: dict) -> None:
        """
        Send a JSON event to every WebSocket subscribed to run_id.
        Disconnected sockets are silently removed.

        Payload shape:
          {
            "event_type": "step_completed",
            "run_id": "...",
            "timestamp": "2026-05-24T12:00:00Z",
            "data": {...}
          }
        """
        payload = json.dumps({
            "event_type": event_type,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })

        sockets = list(self._sockets.get(run_id, []))
        dead: list[WebSocket] = []

        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.unregister(run_id, ws)

    # ── DB persistence helpers ─────────────────────────────────────────────────

    async def record_token_usage(
        self,
        db: AsyncSession,
        run_id: str | uuid.UUID,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> TokenUsage:
        """Persist a token usage record; returns the saved ORM instance."""
        if isinstance(run_id, str):
            run_id = uuid.UUID(run_id)

        # BUG 3 fix: compute estimated cost from MODEL_PRICES
        estimated_cost = _compute_cost(model, prompt_tokens, completion_tokens)

        record = TokenUsage(
            run_id=run_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost=estimated_cost,
        )
        db.add(record)
        await db.flush()
        return record

    async def record_tool_call(
        self,
        db: AsyncSession,
        run_step_id: uuid.UUID,
        tool_name: str,
        input: dict,
        output: dict,
    ) -> ToolCall:
        """Persist a tool call record; returns the saved ORM instance."""
        record = ToolCall(
            run_step_id=run_step_id,
            tool_name=tool_name,
            input=input,
            output=output,
        )
        db.add(record)
        await db.flush()
        return record

    async def record_message(
        self,
        db: AsyncSession,
        run_id: str | uuid.UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        """Persist a message record; returns the saved ORM instance."""
        if isinstance(run_id, str):
            run_id = uuid.UUID(run_id)

        record = Message(run_id=run_id, role=role, content=content)
        db.add(record)
        await db.flush()

        await self.broadcast(str(run_id), EVT_MESSAGE_CREATED, {
            "role": role.value,
            "content": content[:200],  # truncate for WS payload
        })
        return record

    async def get_run_summary(self, db: AsyncSession, run_id: uuid.UUID) -> dict:
        """Return aggregated token usage and tool call counts for a run."""
        from sqlalchemy import select, func
        from app.db.models import RunStep

        token_result = await db.execute(
            select(
                func.sum(TokenUsage.prompt_tokens),
                func.sum(TokenUsage.completion_tokens),
                func.sum(TokenUsage.total_tokens),
            ).where(TokenUsage.run_id == run_id)
        )
        tok = token_result.one()

        step_result = await db.execute(
            select(func.count(RunStep.id)).where(RunStep.run_id == run_id)
        )
        steps_count = step_result.scalar() or 0

        tc_result = await db.execute(
            select(func.count(ToolCall.id))
            .join(RunStep, ToolCall.run_step_id == RunStep.id)
            .where(RunStep.run_id == run_id)
        )
        tool_calls_count = tc_result.scalar() or 0

        return {
            "prompt_tokens": tok[0] or 0,
            "completion_tokens": tok[1] or 0,
            "total_tokens": tok[2] or 0,
            "steps": steps_count,
            "tool_calls": tool_calls_count,
        }
