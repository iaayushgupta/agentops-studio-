"""Seed the payment-triage demo workflow (React Flow graph_json)."""
import logging
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import Workflow, WorkflowStatus

logger = logging.getLogger(__name__)

PAYMENT_TRIAGE_GRAPH = {
    "nodes": [
        {"id": "start",        "type": "start",     "position": {"x": 250, "y": 0},   "data": {"label": "Start"}},
        {"id": "intake",       "type": "agent",     "position": {"x": 250, "y": 100},  "data": {"label": "Intake Agent",       "agent": "intake_agent"}},
        {"id": "investigator", "type": "agent",     "position": {"x": 250, "y": 220},  "data": {"label": "Investigator Agent", "agent": "investigator_agent"}},
        {"id": "cond_failure", "type": "condition", "position": {"x": 250, "y": 340},  "data": {"label": "failure_type?",      "field": "failure_type", "cases": {"insufficient_funds": "resolution", "gateway_error": "resolution", "default": "escalation"}}},
        {"id": "resolution",   "type": "agent",     "position": {"x": 100, "y": 460},  "data": {"label": "Resolution Agent",  "agent": "resolution_agent"}},
        {"id": "escalation",   "type": "agent",     "position": {"x": 400, "y": 460},  "data": {"label": "Escalation Agent",  "agent": "escalation_agent"}},
        {"id": "reviewer",     "type": "agent",     "position": {"x": 250, "y": 580},  "data": {"label": "Reviewer Agent",    "agent": "reviewer_agent"}},
        {"id": "cond_score",   "type": "condition", "position": {"x": 250, "y": 700},  "data": {"label": "score >= 7?",       "field": "reviewer_score", "operator": "gte", "threshold": 7, "cases": {"true": "telegram_response", "false": "reviewer_retry"}}},
        {"id": "reviewer_retry","type": "agent",    "position": {"x": 450, "y": 700},  "data": {"label": "Reviewer (retry)",  "agent": "reviewer_agent", "max_retries": 1}},
        {"id": "telegram_response","type": "agent", "position": {"x": 250, "y": 820},  "data": {"label": "Send Telegram",     "agent": "intake_agent",   "action": "send_telegram_message"}},
        {"id": "end",          "type": "end",       "position": {"x": 250, "y": 940},  "data": {"label": "End"}},
    ],
    "edges": [
        {"id": "e1",  "source": "start",         "target": "intake"},
        {"id": "e2",  "source": "intake",         "target": "investigator"},
        {"id": "e3",  "source": "investigator",   "target": "cond_failure"},
        {"id": "e4",  "source": "cond_failure",   "target": "resolution",      "data": {"condition": "insufficient_funds|gateway_error"}},
        {"id": "e5",  "source": "cond_failure",   "target": "escalation",      "data": {"condition": "default"}},
        {"id": "e6",  "source": "resolution",     "target": "reviewer"},
        {"id": "e7",  "source": "escalation",     "target": "reviewer"},
        {"id": "e8",  "source": "reviewer",       "target": "cond_score"},
        {"id": "e9",  "source": "cond_score",     "target": "telegram_response","data": {"condition": "true"}},
        {"id": "e10", "source": "cond_score",     "target": "reviewer_retry",   "data": {"condition": "false"}},
        {"id": "e11", "source": "reviewer_retry", "target": "telegram_response"},
        {"id": "e12", "source": "telegram_response","target": "end"},
    ],
}


async def run() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(Workflow).where(Workflow.name == "Payment Failure Triage")
        )
        if existing.scalar_one_or_none():
            logger.info("Payment triage workflow already seeded — skipping")
            return

        wf = Workflow(
            name="Payment Failure Triage",
            description=(
                "Telegram → Intake → Investigator → Condition(failure_type) → "
                "Resolution|Escalation → Reviewer → Condition(score>=7) → Telegram Response"
            ),
            graph_json=PAYMENT_TRIAGE_GRAPH,
            status=WorkflowStatus.active,
        )
        db.add(wf)
        await db.commit()
        logger.info("Payment triage workflow seeded")
