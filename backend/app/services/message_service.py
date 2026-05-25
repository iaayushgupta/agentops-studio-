import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Message, MessageRole


class MessageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def append(self, run_id: uuid.UUID, role: MessageRole, content: str) -> Message:
        """Persist a message and return the saved record."""
        ...

    async def get_history(self, run_id: uuid.UUID) -> list[Message]:
        """Return all messages for a run ordered by created_at."""
        ...

    async def get_history_as_langchain(self, run_id: uuid.UUID) -> list:
        """Return messages as LangChain HumanMessage/AIMessage/SystemMessage objects."""
        ...
