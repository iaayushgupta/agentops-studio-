"""GraphExecutor — drives a compiled LangGraph app and persists step events."""
import uuid
from typing import Any


class GraphExecutor:
    """
    Wraps a compiled LangGraph app, streams node events, and writes
    RunStep / ToolCall / TokenUsage records to Postgres after each node.
    """

    def __init__(self, compiled_graph: Any, run_id: uuid.UUID, db_session) -> None:
        self.graph = compiled_graph
        self.run_id = run_id
        self.db = db_session

    async def execute(self, initial_state: dict) -> dict:
        """Run the graph to completion; return final state."""
        ...

    async def _on_node_start(self, node_name: str, state: dict) -> uuid.UUID:
        """Create a RunStep record and broadcast a start event over WebSocket."""
        ...

    async def _on_node_end(self, step_id: uuid.UUID, node_name: str, output: dict) -> None:
        """Update the RunStep record and broadcast a complete event over WebSocket."""
        ...

    async def _handle_tool_events(self, step_id: uuid.UUID, events: list) -> None:
        """Persist ToolCall records for any tool invocations that occurred in this step."""
        ...
