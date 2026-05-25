"""Tool for sending Telegram messages from within an agent node."""
from langchain_core.tools import tool
from app.config import settings


@tool
async def send_telegram_message(text: str, chat_id: str | None = None) -> dict:
    """Send a message to the configured Telegram chat."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return {"error": "TELEGRAM_BOT_TOKEN not configured"}

    target_chat = chat_id or settings.TELEGRAM_CHAT_ID
    if not target_chat:
        return {"error": "No chat_id provided and TELEGRAM_CHAT_ID not set"}

    from telegram import Bot
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    msg = await bot.send_message(chat_id=target_chat, text=text)
    return {"message_id": msg.message_id, "chat_id": target_chat}
