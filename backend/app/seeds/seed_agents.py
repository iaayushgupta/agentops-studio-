"""Seed the five demo agents for the payment-triage workflow."""
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
            "You are a quality reviewer for payment failure resolutions. "
            "Review the proposed resolution or escalation and score it from 1-10 on: "
            "accuracy, completeness, and actionability. "
            "Output JSON with keys: reviewer_score (int 1-10), feedback, approved (bool)."
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
        logger.info("Agents seeded (DELETE+INSERT): %d agents", len(AGENTS))
