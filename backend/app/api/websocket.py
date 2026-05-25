"""WebSocket endpoint — live event stream for a run.

Clients connect to /ws/runs/{run_id} and receive JSON events as the graph executes.
ObservabilityService is the singleton that holds the socket registry and is used by
compiler node closures to broadcast events.
"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.observability_service import ObservabilityService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    obs = ObservabilityService()

    await websocket.accept()
    obs.register(run_id, websocket)
    logger.info("WebSocket connected  run=%s", run_id)

    try:
        while True:
            # Block until client sends something; only "ping" is meaningful.
            # Timeout keeps the loop from sleeping forever when the run completes.
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        obs.unregister(run_id, websocket)
        logger.info("WebSocket disconnected run=%s", run_id)
