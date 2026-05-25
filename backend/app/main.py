import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import engine
from app.api import agents, workflows, runs, websocket

logger = logging.getLogger(__name__)


async def _run_migrations() -> None:
    """Run `alembic upgrade head` as a proper async subprocess.

    Raises RuntimeError on non-zero exit so the lifespan aborts before
    seeds try to touch a schema that may be missing columns.
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "alembic", "upgrade", "head",
        cwd="/app",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    err = stderr.decode().strip()

    if proc.returncode != 0:
        raise RuntimeError(f"Alembic migration failed (exit {proc.returncode}):\n{err}")

    logger.info("Migrations: %s", out or "already at head")
    if err:
        # alembic writes INFO lines to stderr — log them at DEBUG so they're
        # visible without polluting the INFO stream
        logger.debug("Alembic stderr: %s", err)


async def _seed_data() -> None:
    """Run all three seed modules in dependency order.

    Any exception propagates to the lifespan so a broken seed is immediately
    visible in the logs rather than silently swallowed.
    """
    from app.seeds.seed_mock_data import run as seed_mock
    from app.seeds.seed_agents import run as seed_agents
    from app.seeds.seed_workflows import run as seed_workflows

    await seed_mock()       # mock_transactions, mock_psp_status, mock_routing_logs
    await seed_agents()     # agents (referenced by workflows)
    await seed_workflows()  # workflows (reference agents by name)
    logger.info("Seed data loaded")


async def _start_telegram_polling() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.info("TELEGRAM_BOT_TOKEN not set — skipping Telegram polling")
        return
    from app.channels.telegram.handler import start_polling
    asyncio.create_task(start_polling(), name="telegram-polling")
    logger.info("Telegram polling task scheduled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)

    # Step 1 — migrations must succeed before anything touches the DB
    await _run_migrations()

    # Step 2 — seeds run only after schema is confirmed up-to-date
    await _seed_data()

    # Step 3 — background channel polling (non-critical; errors logged, not raised)
    try:
        await _start_telegram_polling()
    except Exception as exc:
        logger.error("Telegram polling failed to start: %s", exc)

    yield  # ← server is live from here

    await engine.dispose()


app = FastAPI(
    title="Yuno Agent Platform",
    description="AI Agent Orchestration Platform",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
app.include_router(runs.router, prefix="/runs", tags=["runs"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
