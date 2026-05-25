"""Seed mock payment data into Postgres.

Transactions cover all routing paths the demo workflow exercises:
  PSP_TIMEOUT      → investigator classifies as PSP_TIMEOUT    → routes to Resolution
  CARD_DECLINE     → investigator classifies as CARD_DECLINE   → routes to Escalation
  INSUFFICIENT_FUNDS → investigator classifies as INSUFFICIENT_FUNDS → routes to Resolution

All seeding uses DELETE + INSERT per row to guarantee clean, duplicate-free state
on every re-run.
"""
import logging
from sqlalchemy import delete, select
from app.db.session import AsyncSessionLocal
from app.db.models import MockTransaction, MockPspStatus, MockRoutingLog

logger = logging.getLogger(__name__)


# ── Fixture data ───────────────────────────────────────────────────────────────

PSP_DATA = [
    {"psp_name": "stripe",    "status": "operational", "latency_ms": 120, "error_rate": 0.01},
    {"psp_name": "adyen",     "status": "degraded",    "latency_ms": 820, "error_rate": 0.18},
    {"psp_name": "braintree", "status": "degraded",    "latency_ms": 450, "error_rate": 0.12},
    {"psp_name": "checkout",  "status": "operational", "latency_ms": 140, "error_rate": 0.02},
]

TRANSACTION_DATA = [
    # ── PSP_TIMEOUT (3 rows) ── investigator → PSP_TIMEOUT → Resolution
    {
        "transaction_id": "TXN-0001",
        "amount": 150.00, "currency": "USD",
        "status": "failed", "psp": "braintree",
        "failure_reason": "gateway_timeout",
        "extra": {"card_last4": "4242", "country": "US", "error_code": "PSP_TIMEOUT"},
    },
    {
        "transaction_id": "TXN-0002",
        "amount": 89.99, "currency": "EUR",
        "status": "failed", "psp": "braintree",
        "failure_reason": "gateway_timeout",
        "extra": {"card_last4": "1234", "country": "DE", "error_code": "PSP_TIMEOUT"},
    },
    {
        "transaction_id": "TXN-0003",
        "amount": 500.00, "currency": "GBP",
        "status": "failed", "psp": "adyen",
        "failure_reason": "gateway_timeout",
        "extra": {"card_last4": "5678", "country": "GB", "error_code": "PSP_TIMEOUT"},
    },
    # ── CARD_DECLINE (2 rows) ── investigator → CARD_DECLINE → Escalation
    {
        "transaction_id": "TXN-0004",
        "amount": 299.00, "currency": "USD",
        "status": "failed", "psp": "stripe",
        "failure_reason": "card_decline",
        "extra": {"card_last4": "0000", "country": "US", "error_code": "CARD_DECLINE"},
    },
    {
        "transaction_id": "TXN-0005",
        "amount": 75.50, "currency": "USD",
        "status": "failed", "psp": "checkout",
        "failure_reason": "card_decline",
        "extra": {"card_last4": "9999", "country": "CA", "error_code": "CARD_DECLINE"},
    },
    # ── INSUFFICIENT_FUNDS (2 rows) ── investigator → INSUFFICIENT_FUNDS → Resolution
    {
        "transaction_id": "TXN-0006",
        "amount": 320.00, "currency": "USD",
        "status": "failed", "psp": "adyen",
        "failure_reason": "insufficient_funds",
        "extra": {"card_last4": "1111", "country": "US", "error_code": "INSUFFICIENT_FUNDS"},
    },
    {
        "transaction_id": "TXN-0007",
        "amount": 49.99, "currency": "EUR",
        "status": "failed", "psp": "stripe",
        "failure_reason": "insufficient_funds",
        "extra": {"card_last4": "2222", "country": "FR", "error_code": "INSUFFICIENT_FUNDS"},
    },
]

ROUTING_LOG_DATA = [
    # TXN-0001 — PSP_TIMEOUT: braintree timed out
    {"transaction_id": "TXN-0001", "from_psp": None,        "to_psp": "braintree", "reason": "initial_routing", "success": False},
    # TXN-0002 — PSP_TIMEOUT: braintree timed out
    {"transaction_id": "TXN-0002", "from_psp": None,        "to_psp": "braintree", "reason": "initial_routing", "success": False},
    # TXN-0003 — PSP_TIMEOUT: initial braintree attempt failed, failover to adyen also failed
    {"transaction_id": "TXN-0003", "from_psp": None,        "to_psp": "braintree", "reason": "initial_routing", "success": False},
    {"transaction_id": "TXN-0003", "from_psp": "braintree", "to_psp": "adyen",     "reason": "gateway_timeout", "success": False},
    # TXN-0004 — CARD_DECLINE: hard decline on stripe
    {"transaction_id": "TXN-0004", "from_psp": None,        "to_psp": "stripe",    "reason": "initial_routing", "success": False},
    # TXN-0005 — CARD_DECLINE: hard decline on checkout
    {"transaction_id": "TXN-0005", "from_psp": None,        "to_psp": "checkout",  "reason": "initial_routing", "success": False},
    # TXN-0006 — INSUFFICIENT_FUNDS
    {"transaction_id": "TXN-0006", "from_psp": None,        "to_psp": "adyen",     "reason": "initial_routing", "success": False},
    # TXN-0007 — INSUFFICIENT_FUNDS
    {"transaction_id": "TXN-0007", "from_psp": None,        "to_psp": "stripe",    "reason": "initial_routing", "success": False},
]


# ── Seed helpers (DELETE + INSERT — guaranteed clean, no duplicates) ───────────

async def _seed_psps(db) -> None:
    for data in PSP_DATA:
        await db.execute(
            delete(MockPspStatus).where(MockPspStatus.psp_name == data["psp_name"])
        )
        db.add(MockPspStatus(**data))


async def _seed_transactions(db) -> None:
    for data in TRANSACTION_DATA:
        await db.execute(
            delete(MockTransaction).where(
                MockTransaction.transaction_id == data["transaction_id"]
            )
        )
        db.add(MockTransaction(**data))


async def _seed_routing_logs(db) -> None:
    # Delete all existing logs for every transaction_id we're about to (re-)insert,
    # then bulk-insert all rows. This keeps multi-hop logs consistent.
    txn_ids = {d["transaction_id"] for d in ROUTING_LOG_DATA}
    for txn_id in txn_ids:
        await db.execute(
            delete(MockRoutingLog).where(MockRoutingLog.transaction_id == txn_id)
        )
    for data in ROUTING_LOG_DATA:
        db.add(MockRoutingLog(**data))


# ── Entry point ────────────────────────────────────────────────────────────────

async def run() -> None:
    async with AsyncSessionLocal() as db:
        await _seed_psps(db)
        await _seed_transactions(db)
        await _seed_routing_logs(db)
        await db.commit()

    logger.info(
        "Mock data seeded — %d PSPs, %d transactions, %d routing logs",
        len(PSP_DATA), len(TRANSACTION_DATA), len(ROUTING_LOG_DATA),
    )
