"""
Shared pytest fixtures for backend critical-path tests.

All async fixtures/tests work without @pytest.mark.asyncio because
pyproject.toml sets asyncio_mode = "auto".

Test-isolation strategy
-----------------------
Two complementary layers keep the real Postgres DB clean:

1. cleanup_test_agents (session-scoped, autouse)
   Runs ONCE at the start of the test session. Deletes any leftover
   "crud_test_agent_*" rows that survived a previous interrupted run.
   The five demo agents are protected (their names are in _SEEDED_NAMES).

2. rollback_after_test (function-scoped, autouse)
   Before each test it overrides FastAPI's get_db dependency to inject a
   shared per-test DB session.  Route handlers flush (making writes visible
   within the transaction) but never commit.  After the test the session is
   rolled back, undoing every INSERT / UPDATE / DELETE made via the HTTP API.

   Tests that call _execute_run() directly use their own AsyncSessionLocal
   sessions (not covered by the override), but those create only run-keyed
   rows (UUIDs) and do not pollute agent-specific queries.
"""
from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

from app.db.models import Agent, Workflow, WorkflowStatus
from app.db.session import AsyncSessionLocal, get_db
from app.main import app


# ── Event loop (session-scoped) ───────────────────────────────────────────────
# asyncpg connections are tied to a specific event loop. Without a
# session-scoped loop, each test gets its own loop, causing
# "Future attached to a different loop" errors when the connection pool
# tries to reuse connections across tests.

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop shared across the entire test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ── Test-isolation helpers ────────────────────────────────────────────────────

# All seeded demo agents that must never be deleted by cleanup fixtures.
_SEEDED_NAMES = frozenset({
    # Payment Failure Triage
    "intake_agent",
    "investigator_agent",
    "resolution_agent",
    "escalation_agent",
    "reviewer_agent",
    # Support Escalation
    "support_triage_agent",
    "tier1_support_agent",
    "tier2_support_agent",
    # Fraud Detection
    "fraud_analyzer_agent",
    "risk_scorer_agent",
    "alert_agent",
})


@pytest.fixture(scope="session", autouse=True)
async def cleanup_test_agents():
    """
    One-time cleanup at session start: delete any non-seeded agents that
    survived a previous interrupted test run.  Runs again at session end for
    symmetry.  Seeded demo agents (_SEEDED_NAMES) are always preserved.
    """
    async def _purge() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(Agent).where(Agent.name.notin_(_SEEDED_NAMES))
            )
            await db.commit()

    await _purge()   # before any test runs
    yield
    await _purge()   # after all tests finish


@pytest.fixture
async def db_session():
    """
    Per-test async DB session.  All writes are flushed (visible within the
    same connection/transaction) but never committed to the database.
    rollback_after_test calls session.rollback() in teardown to discard
    every change the test made.
    """
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
async def rollback_after_test(db_session):
    """
    Override FastAPI's get_db so every HTTPX-driven API call within this test
    uses the same transactional db_session.  The override flushes after each
    request (making writes visible within the transaction) but never commits.
    After the test, db_session.rollback() discards all changes.

    Tests that call _execute_run() directly use their own AsyncSessionLocal
    sessions, so their run/step/message rows are committed but do not affect
    agent-name uniqueness constraints.
    """
    async def _get_db_override():
        try:
            yield db_session
            # Flush so subsequent requests within the same test can see the
            # write (same-connection reads see uncommitted data in Postgres).
            await db_session.flush()
        except Exception:
            # Let FastAPI's exception handler produce the appropriate response.
            # rollback_after_test will call session.rollback() in teardown,
            # recovering the session from any PostgreSQL error state.
            raise

    app.dependency_overrides[get_db] = _get_db_override
    yield
    # --- teardown ---
    app.dependency_overrides.pop(get_db, None)
    await db_session.rollback()


# ── Mock LLM helpers ──────────────────────────────────────────────────────────

# Fixed JSON responses that satisfy every agent's routing requirements:
#   intake_agent     → sets transaction_id
#   investigator     → sets failure_type = "gateway_error" → routes to resolution
#   resolution_agent → sets customer_message (final_response) + confidence
#   reviewer_agent   → sets reviewer_score = 8 (≥7) → routes to telegram_response
#   telegram_response (intake_agent reused) → sets transaction_id (end-path)

MOCK_RESPONSES = [
    # 0 – intake_agent
    '{"transaction_id": "TXN-001", "merchant_name": "TestMerchant", '
    '"amount": 150.0, "currency": "USD", "issue_description": "gateway timeout"}',
    # 1 – investigator_agent
    '{"failure_type": "gateway_error", "summary": "PSP timeout on braintree gateway", '
    '"transaction_id": "TXN-001"}',
    # 2 – resolution_agent  (also works for escalation_agent path)
    '{"resolution_type": "RETRY_ALTERNATE_PSP", "recommended_psp": "adyen", '
    '"reason": "Gateway timeout — retry with Adyen", '
    '"customer_message": "Your $150 payment failed due to a gateway timeout. '
    'We are retrying via an alternate processor.", "confidence": 0.9}',
    # 3 – reviewer_agent  (score=8 → passes ≥7 gate)
    '{"reviewer_score": 8, "feedback": "Clear and actionable resolution.", "approved": true}',
    # 4 – telegram_response node (uses intake_agent in seed graph)
    '{"transaction_id": "TXN-001", "merchant_name": "TestMerchant", '
    '"amount": 150.0, "currency": "USD", "issue_description": "resolved"}',
]


class _FakeAIMessage:
    """Minimal duck-typed AIMessage for compiler consumption."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls: list = []
        self.usage_metadata = {"input_tokens": 100, "output_tokens": 50}


class _MockLLM:
    """
    Cycles through MOCK_RESPONSES on successive ainvoke() calls.
    bind_tools() returns self so the LLM+tool plumbing in compiler.py works.
    """

    def __init__(self) -> None:
        self._call_count = 0

    def bind_tools(self, tools):  # noqa: ANN001
        return self

    async def ainvoke(self, messages):  # noqa: ANN001
        idx = self._call_count % len(MOCK_RESPONSES)
        self._call_count += 1
        return _FakeAIMessage(MOCK_RESPONSES[idx])


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def async_client():
    """HTTPX async client wired to the FastAPI app (no real network)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_llm(mocker):  # noqa: ANN001
    """
    Patch app.runtime.compiler.get_llm to return a _MockLLM instance.
    All agent nodes within one test share the same instance so the call
    counter advances correctly across the workflow execution.
    """
    llm = _MockLLM()
    mocker.patch("app.runtime.compiler.get_llm", return_value=llm)
    return llm


@pytest.fixture
async def seeded_agents() -> dict[str, Agent]:
    """
    Ensure all 5 demo agents are present in the DB (idempotent upsert).
    Returns a name → Agent mapping.
    """
    from app.seeds.seed_agents import AGENTS as AGENT_DEFS

    agents: dict[str, Agent] = {}
    async with AsyncSessionLocal() as db:
        for agent_data in AGENT_DEFS:
            result = await db.execute(
                select(Agent).where(Agent.name == agent_data["name"])
            )
            agent = result.scalar_one_or_none()
            if agent is None:
                agent = Agent(**agent_data)
                db.add(agent)
                await db.flush()
                await db.refresh(agent)
            agents[agent.name] = agent
        await db.commit()
    return agents


@pytest.fixture
async def payment_triage_workflow(seeded_agents) -> Workflow:  # noqa: ANN001
    """
    Ensure the Payment Failure Triage workflow is present and active.
    Returns a detached Workflow instance.
    """
    from app.seeds.seed_workflows import PAYMENT_TRIAGE_GRAPH

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workflow).where(Workflow.name == "Payment Failure Triage")
        )
        wf = result.scalar_one_or_none()
        if wf is None:
            wf = Workflow(
                name="Payment Failure Triage",
                description="Demo payment triage workflow",
                graph_json=PAYMENT_TRIAGE_GRAPH,
                status=WorkflowStatus.active,
            )
            db.add(wf)
            await db.flush()
            await db.refresh(wf)
        wf_id = wf.id
        await db.commit()

    # Re-fetch in a clean session to avoid DetachedInstanceError
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workflow).where(Workflow.id == wf_id))
        return result.scalar_one()
