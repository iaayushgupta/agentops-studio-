import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Agent


class AgentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_name(self, name: str) -> Agent | None:
        """Return the agent with the given name, or None."""
        ...

    async def list_all(self) -> list[Agent]:
        """Return all agents ordered by name."""
        ...

    async def upsert(self, name: str, **fields) -> Agent:
        """Create or update an agent by name; return the persisted instance."""
        ...
