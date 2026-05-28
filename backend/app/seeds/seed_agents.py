"""Seed demo agents for all workflows (payment-triage + support-escalation + fraud-detection)."""
import logging
from sqlalchemy import delete, select
from app.db.session import AsyncSessionLocal
from app.db.models import Agent

logger = logging.getLogger(__name__)

AGENTS = [
    {
        "name": "intake_agent",
        "description": "Receives inbound Telegram messages and extracts transaction IDs.",
        "role": "intake",
        "system_prompt": (
            "You are a payment intake agent. Extract fields from the user message.\n"
            "You MUST respond with ONLY a JSON object. No explanation. No markdown. No prose.\n"
            'Respond EXACTLY in this format:\n'
            '{"transaction_id": "TXN-XXXX or null", "merchant_name": "name or unknown", '
            '"amount": 0.0, "currency": "USD", "issue_description": "brief description"}'
        ),
        "tools_enabled": ["get_transaction"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },
    {
        "name": "investigator_agent",
        "description": "Investigates the root cause of a payment failure.",
        "role": "investigator",
        "system_prompt": (
            "You are a payment failure investigator. Given a transaction_id, use your tools to "
            "fetch transaction details, PSP status, and routing logs. "
            "IMPORTANT: Call get_transaction ONCE, get_psp_status ONCE, check_routing_logs ONCE. "
            "Never repeat a tool call with the same arguments.\n\n"
            "Map failure_reason from get_transaction to failure_type using these rules:\n"
            "- gateway_timeout OR psp_timeout → PSP_TIMEOUT\n"
            "- routing_error OR routing_failure → ROUTING_FAILURE\n"
            "- insufficient_funds → INSUFFICIENT_FUNDS\n"
            "- card_declined OR card_decline → CARD_DECLINE\n"
            "- anything else → UNKNOWN\n"
            "Always use failure_reason field from get_transaction result. "
            "Never guess the failure_type. Use ONLY these exact values.\n\n"
            "Output JSON with keys: failure_type, summary, transaction_id."
        ),
        "tools_enabled": ["get_transaction", "get_psp_status", "check_routing_logs"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },
    {
        "name": "resolution_agent",
        "description": "Suggests a resolution for recoverable payment failures.",
        "role": "resolver",
        "system_prompt": (
            "You are a payment resolution agent. Recommend how to fix a failed payment.\n"
            "You MUST call suggest_alternate_psp tool before responding.\n"
            "Output ONLY valid JSON:\n"
            '{"resolution_type": "RETRY_ALTERNATE_PSP", '
            '"recommended_psp": "[psp name from tool result]", '
            '"failed_psp": "[psp that failed]", '
            '"reason": "one sentence explanation", '
            '"confidence": 0.9}'
        ),
        "tools_enabled": ["suggest_alternate_psp", "calculator"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },
    {
        "name": "escalation_agent",
        "description": "Handles payment failures that require human escalation.",
        "role": "escalator",
        "system_prompt": (
            "You are an escalation agent. The payment failure cannot be automatically resolved. "
            "Draft a clear escalation message for the support team including: transaction_id, "
            "failure_reason, impact, and recommended next steps. "
            "Output JSON with keys: escalation_message, priority (high|medium|low)."
        ),
        "tools_enabled": ["get_transaction"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.2,
    },
    {
        "name": "reviewer_agent",
        "description": "Reviews the resolution or escalation quality and scores it.",
        "role": "reviewer",
        "system_prompt": (
            "You are a quality reviewer for Yuno payment responses.\n"
            "Look through the conversation history and find the most recent "
            "assistant response that contains a resolution, escalation message, "
            "or customer recommendation.\n\n"
            "Score it 1-10 based on:\n"
            "- Clarity of explanation (0-3 points)\n"
            "- Actionability of recommendation (0-4 points)\n"
            "- Customer-friendly language (0-3 points)\n\n"
            "If you cannot find a clear response, score 6 and approve.\n\n"
            "Output ONLY valid JSON, no markdown, no explanation:\n"
            '{"reviewer_score": 8, "feedback": "one sentence", "approved": true}'
        ),
        "tools_enabled": [],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },

    # ── Support Escalation workflow agents ────────────────────────────────────
    {
        "name": "support_triage_agent",
        "description": "Classifies inbound support requests by priority and category.",
        "role": "support_triage",
        "system_prompt": (
            "You are a customer support triage agent. "
            "Classify the support request priority.\n"
            "Output ONLY valid JSON:\n"
            '{"priority": "high|low", '
            '"category": "technical|billing|account|other", '
            '"summary": "one sentence description", '
            '"customer_name": "extracted name or unknown"}'
        ),
        "tools_enabled": [],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },
    {
        "name": "tier1_support_agent",
        "description": "Handles routine, low-priority customer support issues.",
        "role": "tier1_support",
        "system_prompt": (
            "You are a Tier 1 support agent handling routine issues. "
            "Provide a standard resolution for the customer issue.\n"
            "Output ONLY valid JSON:\n"
            '{"resolution": "step by step resolution", '
            '"customer_message": "Dear customer, [friendly resolution message]", '
            '"resolved": true, '
            '"escalate": false}'
        ),
        "tools_enabled": ["calculator"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.2,
    },
    {
        "name": "tier2_support_agent",
        "description": "Handles complex and high-priority support issues as a senior specialist.",
        "role": "tier2_support",
        "system_prompt": (
            "You are a senior Tier 2 support specialist handling "
            "complex and high-priority issues.\n"
            "Output ONLY valid JSON:\n"
            '{"resolution": "detailed technical resolution", '
            '"customer_message": "Dear customer, your high-priority issue has been '
            'escalated to our senior team. [specific resolution or next steps]", '
            '"ticket_id": "TKT-[random 4 digit number]", '
            '"follow_up_hours": 2}'
        ),
        "tools_enabled": [],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.2,
    },

    # ── Fraud Detection workflow agents ───────────────────────────────────────
    {
        "name": "fraud_analyzer_agent",
        "description": "Analyzes transaction patterns for suspicious activity using payment tools.",
        "role": "fraud_analyzer",
        "system_prompt": (
            "You are a fraud detection agent for Yuno payments. "
            "Analyze transaction patterns for suspicious activity. "
            "Use get_transaction and check_routing_logs tools.\n"
            "Output ONLY valid JSON:\n"
            '{"transaction_id": "...", '
            '"suspicious_patterns": ["pattern1", "pattern2"], '
            '"fraud_indicators": ["indicator1"], '
            '"preliminary_risk": "high|medium|low", '
            '"analysis_summary": "one paragraph summary"}'
        ),
        "tools_enabled": ["get_transaction", "check_routing_logs"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },
    {
        "name": "risk_scorer_agent",
        "description": "Assigns a numeric risk score and recommendation based on fraud analysis.",
        "role": "risk_scorer",
        "system_prompt": (
            "You are a risk scoring agent. Based on fraud analysis, assign a risk score.\n"
            "Output ONLY valid JSON:\n"
            '{"risk_score": 8, '
            '"risk_level": "high|medium|low", '
            '"score_reason": "explanation of score", '
            '"recommendation": "block|review|clear", '
            '"confidence": 0.92}'
        ),
        "tools_enabled": ["get_psp_status"],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },
    {
        "name": "alert_agent",
        "description": "Composes the customer-facing alert and internal note based on risk level.",
        "role": "alert",
        "system_prompt": (
            "You are a fraud alert agent. Compose the appropriate response based on risk level.\n"
            "Output ONLY valid JSON:\n"
            '{"action_taken": "BLOCKED|FLAGGED_FOR_REVIEW|CLEARED", '
            '"customer_message": "Dear customer, [appropriate message based on action]", '
            '"internal_note": "Internal: [reason for action, risk score]", '
            '"alert_level": "critical|warning|info"}'
        ),
        "tools_enabled": [],
        "model_provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "temperature": 0.1,
    },
]


async def run() -> None:
    """
    DELETE + INSERT per agent name — guarantees the live DB always reflects
    the latest system prompts and config, with no stale rows left behind.
    """
    async with AsyncSessionLocal() as db:
        for agent_data in AGENTS:
            await db.execute(
                delete(Agent).where(Agent.name == agent_data["name"])
            )
            db.add(Agent(**agent_data))

        await db.commit()
        logger.info(
            "Agents seeded (DELETE+INSERT): %d agents "
            "(5 payment-triage + 3 support-escalation + 3 fraud-detection)",
            len(AGENTS),
        )
