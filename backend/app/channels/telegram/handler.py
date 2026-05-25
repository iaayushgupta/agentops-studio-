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
        """Trigger the payment-triage workflow for each inbound message."""
        from app.db.session import AsyncSessionLocal
        from app.services.runtime_service import RuntimeService
        from sqlalchemy import select
        from app.db.models import Workflow, WorkflowStatus

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Workflow)
                .where(Workflow.status == WorkflowStatus.active)
                .limit(1)
            )
            workflow = result.scalar_one_or_none()
            if workflow is None:
                logger.warning("No active workflow found for Telegram message")
                return
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
