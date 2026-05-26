"""Telegram async polling adapter — runs as an asyncio background task."""
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from app.channels.base import ChannelAdapter
from app.config import settings

logger = logging.getLogger(__name__)

_app: Application | None = None


class TelegramAdapter(ChannelAdapter):
    def __init__(self) -> None:
        self._app: Application | None = None

    async def start(self) -> None:
        self._app = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN)
            .build()
        )
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram polling active")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send(self, recipient: str, text: str) -> None:
        if self._app:
            await self._app.bot.send_message(chat_id=recipient, text=text)

    async def on_message(self, sender: str, text: str, raw: dict) -> None:
        """
        Route the inbound message to the best-matching active workflow.

        Routing order:
          1. Load active RoutingRule rows from the DB ordered by priority DESC.
          2. For each rule, check if any keyword appears in the message (case-insensitive).
             The first matching rule's workflow is used.
          3. Fallback: first active workflow (any) when no rule matches.

        Rules are managed via the Settings UI (GET/POST/PUT/DELETE /routing-rules).
        """
        from app.db.session import AsyncSessionLocal
        from app.services.runtime_service import RuntimeService
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.db.models import RoutingRule, Workflow, WorkflowStatus

        async with AsyncSessionLocal() as db:
            # ── 1. Fetch active routing rules (DB-driven) ─────────────────────
            result = await db.execute(
                select(RoutingRule)
                .options(selectinload(RoutingRule.workflow))
                .where(RoutingRule.is_active == True)  # noqa: E712
                .order_by(RoutingRule.priority.desc())
            )
            active_rules = result.scalars().all()

            # ── 2. First-match keyword routing ────────────────────────────────
            message_lower = text.lower()
            workflow = None
            for rule in active_rules:
                wf = rule.workflow
                if wf is None or wf.status != WorkflowStatus.active:
                    continue
                if any(kw.lower() in message_lower for kw in (rule.keywords or [])):
                    workflow = wf
                    logger.info(
                        "Routing rule matched (priority=%s, keywords=%s) → workflow '%s'",
                        rule.priority, rule.keywords, wf.name,
                    )
                    break

            # ── 3. Fallback: first active workflow ────────────────────────────
            if workflow is None:
                logger.info(
                    "No routing rule matched message from %s; "
                    "falling back to first active workflow",
                    sender,
                )
                fb = await db.execute(
                    select(Workflow)
                    .where(Workflow.status == WorkflowStatus.active)
                    .limit(1)
                )
                workflow = fb.scalar_one_or_none()

            if workflow is None:
                logger.warning("No active workflow found for Telegram message from %s", sender)
                return

            logger.info(
                "Telegram message from %s → workflow '%s' (id=%s)",
                sender, workflow.name, workflow.id,
            )
            await RuntimeService(db).trigger_run(
                workflow_id=workflow.id,
                trigger_channel="telegram",
                trigger_payload={"sender": sender, "text": text, "raw": raw},
            )
            # Must commit here: trigger_run only flushes. Without an explicit commit the
            # Run row is rolled back when this session closes, and the background
            # _execute_run task (which opens its own session) can't find it.
            await db.commit()

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message and update.message.text:
            await self.on_message(
                sender=str(update.message.chat_id),
                text=update.message.text,
                raw=update.message.to_dict(),
            )


_adapter = TelegramAdapter()


async def start_polling() -> None:
    """Entry-point called from main.py lifespan."""
    await _adapter.start()


async def send_response(chat_id: str, text: str) -> None:
    """
    Send an outbound message back to a Telegram chat.
    Called by RuntimeService._execute_run after the graph completes.
    No-ops gracefully if the adapter is not started.
    """
    if _adapter._app is None:
        logger.warning("Telegram adapter not started — cannot reply to chat %s", chat_id)
        return
    try:
        await _adapter.send(chat_id, text)
    except Exception as exc:
        logger.error("Telegram send_response failed for chat %s: %s", chat_id, exc)
