import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Workflow, WorkflowStatus


class WorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, workflow_id: uuid.UUID) -> Workflow | None:
        """Fetch a workflow by ID."""
        ...

    async def activate(self, workflow_id: uuid.UUID) -> Workflow:
        """Set workflow status to active; validate graph_json is non-empty."""
        ...

    async def compile_graph(self, workflow: Workflow):
        """Return a compiled LangGraph StateGraph from workflow.graph_json."""
        ...
