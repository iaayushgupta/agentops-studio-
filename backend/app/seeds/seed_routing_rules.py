"""Seed 3 default keyword routing rules for Telegram message routing.

Idempotent — skips if any rules already exist.
Must run AFTER seed_workflows.py so the referenced workflow IDs are available.
"""
import logging
from sqlalchemy import select, func

from app.db.session import AsyncSessionLocal
from app.db.models import RoutingRule, Workflow

logger = logging.getLogger(__name__)

# ── Default rules ──────────────────────────────────────────────────────────────
# Each rule has: keywords, name_pattern (ILIKE match against Workflow.name), priority

_DEFAULT_RULES = [
    {
        "keywords": ["payment", "transaction", "TXN", "failed", "charged"],
        "name_pattern": "%payment%",
        "priority": 1,
    },
    {
        "keywords": ["urgent", "down", "support", "help", "account", "login"],
        "name_pattern": "%support%",
        "priority": 2,
    },
    {
        "keywords": ["fraud", "suspicious", "verify", "unauthorized", "alert"],
        "name_pattern": "%fraud%",
        "priority": 3,
    },
]


async def run() -> None:
    async with AsyncSessionLocal() as db:
        # Idempotent: skip if any rules already exist
        count = (
            await db.execute(select(func.count()).select_from(RoutingRule))
        ).scalar_one()
        if count > 0:
            logger.info("Routing rules already seeded (%d rows) — skipping", count)
            return

        inserted = 0
        for rule_def in _DEFAULT_RULES:
            # Resolve workflow by name pattern
            result = await db.execute(
                select(Workflow).where(Workflow.name.ilike(rule_def["name_pattern"])).limit(1)
            )
            workflow = result.scalar_one_or_none()
            if workflow is None:
                logger.warning(
                    "Seed routing rule: no workflow matching '%s' — rule will have no target",
                    rule_def["name_pattern"],
                )

            db.add(
                RoutingRule(
                    keywords=rule_def["keywords"],
                    workflow_id=workflow.id if workflow else None,
                    priority=rule_def["priority"],
                    is_active=True,
                )
            )
            inserted += 1

        await db.commit()
        logger.info("Seeded %d routing rules", inserted)
