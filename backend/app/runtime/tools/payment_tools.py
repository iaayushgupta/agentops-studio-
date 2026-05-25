"""Payment domain tools backed by Postgres mock tables."""
from langchain_core.tools import tool
from sqlalchemy import select, text, func
from app.db.session import AsyncSessionLocal
from app.db.models import MockTransaction, MockPspStatus, MockRoutingLog


@tool
async def get_transaction(transaction_id: str) -> dict:
    """Fetch a mock payment transaction by its transaction_id."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MockTransaction).where(MockTransaction.transaction_id == transaction_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"error": f"Transaction {transaction_id} not found"}
        return {
            "transaction_id": row.transaction_id,
            "amount": row.amount,
            "currency": row.currency,
            "status": row.status,
            "psp": row.psp,
            "failure_reason": row.failure_reason,
            "extra": row.extra,
        }


@tool
async def get_psp_status(psp_name: str) -> dict:
    """Return operational status, latency, and error rate for a PSP."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            # BUG 5 fix: case-insensitive PSP name lookup
            select(MockPspStatus).where(func.lower(MockPspStatus.psp_name) == psp_name.lower())
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"error": f"PSP {psp_name} not found"}
        return {
            "psp_name": row.psp_name,
            "status": row.status,
            "latency_ms": row.latency_ms,
            "error_rate": row.error_rate,
        }


@tool
async def check_routing_logs(transaction_id: str) -> list[dict]:
    """Return routing history for a transaction."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MockRoutingLog)
            .where(MockRoutingLog.transaction_id == transaction_id)
            .order_by(MockRoutingLog.created_at)
        )
        rows = result.scalars().all()
        return [
            {
                "from_psp": r.from_psp,
                "to_psp": r.to_psp,
                "reason": r.reason,
                "success": r.success,
            }
            for r in rows
        ]


@tool
async def suggest_alternate_psp(current_psp: str) -> dict:
    """Suggest an alternate PSP with lower error rate than the current one."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MockPspStatus)
            .where(MockPspStatus.psp_name != current_psp)
            .where(MockPspStatus.status == "operational")
            .order_by(MockPspStatus.error_rate)
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"error": "No alternate PSP available"}
        return {"suggested_psp": row.psp_name, "error_rate": row.error_rate, "latency_ms": row.latency_ms}
