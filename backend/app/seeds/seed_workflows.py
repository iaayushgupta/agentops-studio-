"""Seed all three demo workflows (payment-triage + support-escalation + fraud-detection).

Graph format notes
------------------
PAYMENT_TRIAGE_GRAPH  — old ReactFlow format (id/type/data, source/target edges)
SUPPORT_ESCALATION_GRAPH, FRAUD_DETECTION_GRAPH — backend-native format
  (node_id/node_type/config_json, source_node_id/target_node_id edges, top-level entry_node)

The compiler normalises both formats automatically.
"""
import logging
from sqlalchemy import delete
from app.db.session import AsyncSessionLocal
from app.db.models import Workflow, WorkflowStatus

logger = logging.getLogger(__name__)


# ── Payment Failure Triage (old ReactFlow format — kept as-is) ────────────────

PAYMENT_TRIAGE_GRAPH = {
    "nodes": [
        {"id": "start",         "type": "start",     "position": {"x": 250, "y": 0},   "data": {"label": "Start"}},
        {"id": "intake",        "type": "agent",     "position": {"x": 250, "y": 100},  "data": {"label": "Intake Agent",       "agent": "intake_agent"}},
        {"id": "investigator",  "type": "agent",     "position": {"x": 250, "y": 220},  "data": {"label": "Investigator Agent", "agent": "investigator_agent"}},
        {"id": "cond_failure",  "type": "condition", "position": {"x": 250, "y": 340},  "data": {"label": "failure_type?",      "field": "failure_type", "cases": {"insufficient_funds": "resolution", "gateway_error": "resolution", "default": "escalation"}}},
        {"id": "resolution",    "type": "agent",     "position": {"x": 100, "y": 460},  "data": {"label": "Resolution Agent",   "agent": "resolution_agent"}},
        {"id": "escalation",    "type": "agent",     "position": {"x": 400, "y": 460},  "data": {"label": "Escalation Agent",   "agent": "escalation_agent"}},
        {"id": "reviewer",      "type": "agent",     "position": {"x": 250, "y": 580},  "data": {"label": "Reviewer Agent",     "agent": "reviewer_agent"}},
        {"id": "cond_score",    "type": "condition", "position": {"x": 250, "y": 700},  "data": {"label": "score >= 7?",        "field": "reviewer_score", "operator": "gte", "threshold": 7, "cases": {"true": "telegram_response", "false": "reviewer_retry"}}},
        {"id": "reviewer_retry","type": "agent",     "position": {"x": 450, "y": 700},  "data": {"label": "Reviewer (retry)",   "agent": "reviewer_agent", "max_retries": 1}},
        {"id": "telegram_response","type": "agent",  "position": {"x": 250, "y": 820},  "data": {"label": "Send Telegram",      "agent": "intake_agent",   "action": "send_telegram_message"}},
        {"id": "end",           "type": "end",       "position": {"x": 250, "y": 940},  "data": {"label": "End"}},
    ],
    "edges": [
        {"id": "e1",  "source": "start",           "target": "intake"},
        {"id": "e2",  "source": "intake",           "target": "investigator"},
        {"id": "e3",  "source": "investigator",     "target": "cond_failure"},
        {"id": "e4",  "source": "cond_failure",     "target": "resolution",       "data": {"condition": "insufficient_funds|gateway_error"}},
        {"id": "e5",  "source": "cond_failure",     "target": "escalation",       "data": {"condition": "default"}},
        {"id": "e6",  "source": "resolution",       "target": "reviewer"},
        {"id": "e7",  "source": "escalation",       "target": "reviewer"},
        {"id": "e8",  "source": "reviewer",         "target": "cond_score"},
        {"id": "e9",  "source": "cond_score",       "target": "telegram_response","data": {"condition": "true"}},
        {"id": "e10", "source": "cond_score",       "target": "reviewer_retry",   "data": {"condition": "false"}},
        {"id": "e11", "source": "reviewer_retry",   "target": "telegram_response"},
        {"id": "e12", "source": "telegram_response","target": "end"},
    ],
}


# ── Support Escalation (backend-native format) ────────────────────────────────

SUPPORT_ESCALATION_GRAPH = {
    "entry_node": "support_triage",
    "nodes": [
        {
            "node_id": "support_triage",
            "node_type": "agent",
            "position": {"x": 250, "y": 80},
            "config_json": {
                "label": "Support Triage",
                "agent_name": "support_triage_agent",
                "agent_role": "support_triage",
            },
        },
        {
            "node_id": "cond_priority",
            "node_type": "condition",
            "position": {"x": 250, "y": 220},
            "config_json": {
                "label": "priority?",
                "field": "priority",
                "cases": {
                    "high": "tier2_support",
                    "low": "tier1_support",
                    "default": "tier1_support",
                },
            },
        },
        {
            "node_id": "tier1_support",
            "node_type": "agent",
            "position": {"x": 80, "y": 360},
            "config_json": {
                "label": "Tier 1 Support",
                "agent_name": "tier1_support_agent",
                "agent_role": "tier1_support",
            },
        },
        {
            "node_id": "tier2_support",
            "node_type": "agent",
            "position": {"x": 420, "y": 360},
            "config_json": {
                "label": "Tier 2 Support",
                "agent_name": "tier2_support_agent",
                "agent_role": "tier2_support",
            },
        },
        {
            "node_id": "end",
            "node_type": "end",
            "position": {"x": 250, "y": 500},
            "config_json": {"label": "End"},
        },
    ],
    "edges": [
        {
            "source_node_id": "support_triage",
            "target_node_id": "cond_priority",
            "label": "",
        },
        {
            "source_node_id": "cond_priority",
            "target_node_id": "tier1_support",
            "condition_json": {"value": "low"},
            "label": "Low Priority",
        },
        {
            "source_node_id": "cond_priority",
            "target_node_id": "tier2_support",
            "condition_json": {"value": "high"},
            "label": "High Priority",
        },
        {
            "source_node_id": "tier1_support",
            "target_node_id": "end",
            "label": "",
        },
        {
            "source_node_id": "tier2_support",
            "target_node_id": "end",
            "label": "",
        },
    ],
}


# ── Fraud Detection Alert (backend-native format) ─────────────────────────────

FRAUD_DETECTION_GRAPH = {
    "entry_node": "fraud_analyzer",
    "nodes": [
        {
            "node_id": "fraud_analyzer",
            "node_type": "agent",
            "position": {"x": 250, "y": 80},
            "config_json": {
                "label": "Fraud Analyzer",
                "agent_name": "fraud_analyzer_agent",
                "agent_role": "fraud_analyzer",
            },
        },
        {
            "node_id": "risk_scorer",
            "node_type": "agent",
            "position": {"x": 250, "y": 220},
            "config_json": {
                "label": "Risk Scorer",
                "agent_name": "risk_scorer_agent",
                "agent_role": "risk_scorer",
            },
        },
        {
            "node_id": "cond_risk",
            "node_type": "condition",
            "position": {"x": 250, "y": 360},
            "config_json": {
                "label": "risk_level?",
                "field": "risk_level",
                "cases": {
                    "high": "alert",
                    "medium": "alert",
                    "low": "end",
                    "default": "alert",
                },
            },
        },
        {
            "node_id": "alert",
            "node_type": "agent",
            "position": {"x": 250, "y": 500},
            "config_json": {
                "label": "Alert Agent",
                "agent_name": "alert_agent",
                "agent_role": "alert",
            },
        },
        {
            "node_id": "end",
            "node_type": "end",
            "position": {"x": 250, "y": 640},
            "config_json": {"label": "End"},
        },
    ],
    "edges": [
        {
            "source_node_id": "fraud_analyzer",
            "target_node_id": "risk_scorer",
            "label": "",
        },
        {
            "source_node_id": "risk_scorer",
            "target_node_id": "cond_risk",
            "label": "",
        },
        {
            "source_node_id": "cond_risk",
            "target_node_id": "alert",
            "condition_json": {"value": "high"},
            "label": "High / Medium Risk",
        },
        {
            "source_node_id": "cond_risk",
            "target_node_id": "alert",
            "condition_json": {"value": "medium"},
            "label": "Medium Risk",
        },
        {
            "source_node_id": "cond_risk",
            "target_node_id": "end",
            "condition_json": {"value": "low"},
            "label": "Low Risk (clear)",
        },
        {
            "source_node_id": "alert",
            "target_node_id": "end",
            "label": "",
        },
    ],
}


# ── Seeder ────────────────────────────────────────────────────────────────────

_WORKFLOWS = [
    (
        "Payment Failure Triage",
        (
            "Telegram → Intake → Investigator → Condition(failure_type) → "
            "Resolution|Escalation → Reviewer → Condition(score>=7) → Telegram Response"
        ),
        PAYMENT_TRIAGE_GRAPH,
    ),
    (
        "Support Escalation",
        (
            "Triage inbound support requests by priority → "
            "route low-priority to Tier 1 support, high-priority to Tier 2 senior specialist."
        ),
        SUPPORT_ESCALATION_GRAPH,
    ),
    (
        "Fraud Detection Alert",
        (
            "Analyzes transactions for fraud patterns → scores risk → "
            "blocks/flags high-risk transactions and clears low-risk ones."
        ),
        FRAUD_DETECTION_GRAPH,
    ),
]


async def run() -> None:
    """
    DELETE + INSERT per workflow name — guarantees the live DB always reflects
    the latest graph_json and config, with no stale rows left behind.
    """
    async with AsyncSessionLocal() as db:
        for name, description, graph_json in _WORKFLOWS:
            await db.execute(
                delete(Workflow).where(Workflow.name == name)
            )
            db.add(Workflow(
                name=name,
                description=description,
                graph_json=graph_json,
                status=WorkflowStatus.active,
            ))

        await db.commit()
        logger.info(
            "Workflows seeded (DELETE+INSERT): %d workflows "
            "(payment-triage + support-escalation + fraud-detection)",
            len(_WORKFLOWS),
        )
