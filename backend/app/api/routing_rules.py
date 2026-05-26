"""CRUD API for Telegram keyword routing rules.

GET    /routing-rules          — list all rules (ordered by priority DESC)
POST   /routing-rules          — create a new rule
PUT    /routing-rules/{id}     — replace a rule
DELETE /routing-rules/{id}     — remove a rule (204)
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.db.models import RoutingRule, Workflow

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class RoutingRuleCreate(BaseModel):
    keywords: list[str] = Field(..., min_length=1)
    workflow_id: uuid.UUID | None = None
    priority: int = Field(default=0, ge=0)
    is_active: bool = True


class RoutingRuleUpdate(BaseModel):
    keywords: list[str] | None = Field(default=None, min_length=1)
    workflow_id: uuid.UUID | None = None
    priority: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class RoutingRuleResponse(BaseModel):
    id: uuid.UUID
    keywords: list[str]
    workflow_id: uuid.UUID | None
    workflow_name: str | None
    priority: int
    is_active: bool
    created_at: Any

    model_config = {"from_attributes": False}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_rule_or_404(rule_id: uuid.UUID, db: AsyncSession) -> RoutingRule:
    result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.workflow))
        .where(RoutingRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found")
    return rule


def _to_response(rule: RoutingRule) -> RoutingRuleResponse:
    return RoutingRuleResponse(
        id=rule.id,
        keywords=list(rule.keywords or []),
        workflow_id=rule.workflow_id,
        workflow_name=rule.workflow.name if rule.workflow else None,
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[RoutingRuleResponse])
async def list_routing_rules(
    db: AsyncSession = Depends(get_db),
) -> list[RoutingRuleResponse]:
    """Return all routing rules ordered by priority descending (highest first)."""
    result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.workflow))
        .order_by(RoutingRule.priority.desc(), RoutingRule.created_at)
    )
    rules = result.scalars().all()
    return [_to_response(r) for r in rules]


@router.post("", response_model=RoutingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_routing_rule(
    payload: RoutingRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> RoutingRuleResponse:
    # Validate workflow_id if provided
    if payload.workflow_id:
        wf = await db.get(Workflow, payload.workflow_id)
        if wf is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Workflow {payload.workflow_id} not found",
            )

    rule = RoutingRule(
        keywords=payload.keywords,
        workflow_id=payload.workflow_id,
        priority=payload.priority,
        is_active=payload.is_active,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    # Eager-load the workflow for the response
    if rule.workflow_id:
        await db.execute(
            select(RoutingRule)
            .options(selectinload(RoutingRule.workflow))
            .where(RoutingRule.id == rule.id)
        )
        await db.refresh(rule)

    # Re-fetch with relationship
    result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.workflow))
        .where(RoutingRule.id == rule.id)
    )
    rule = result.scalar_one()
    await db.commit()
    return _to_response(rule)


@router.put("/{rule_id}", response_model=RoutingRuleResponse)
async def update_routing_rule(
    rule_id: uuid.UUID,
    payload: RoutingRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> RoutingRuleResponse:
    rule = await _get_rule_or_404(rule_id, db)

    updates = payload.model_dump(exclude_unset=True)

    # Validate new workflow_id if provided
    if "workflow_id" in updates and updates["workflow_id"] is not None:
        wf = await db.get(Workflow, updates["workflow_id"])
        if wf is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Workflow {updates['workflow_id']} not found",
            )

    for field, value in updates.items():
        setattr(rule, field, value)

    await db.flush()

    # Re-fetch with relationship to get updated workflow_name
    result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.workflow))
        .where(RoutingRule.id == rule_id)
    )
    rule = result.scalar_one()
    await db.commit()
    return _to_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routing_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    rule = await _get_rule_or_404(rule_id, db)
    await db.delete(rule)
    await db.commit()
