import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.db.models import Run, RunStatus

router = APIRouter()


class RunCreate(BaseModel):
    workflow_id: uuid.UUID
    trigger_channel: str | None = "api"
    trigger_payload: dict | None = None


class RunResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID | None
    status: RunStatus
    trigger_channel: str | None
    trigger_payload: dict | None
    started_at: Any
    ended_at: Any
    created_at: Any
    total_cost_usd: float | None = None
    error_message: str | None = None
    final_response: str | None = None

    model_config = {"from_attributes": True}


async def _get_run_or_404(run_id: uuid.UUID, db: AsyncSession) -> Run:
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("", response_model=list[RunResponse])
async def list_runs(
    skip: int = 0,
    limit: int = 100,
    workflow_id: uuid.UUID | None = None,
    status: RunStatus | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Run)
    if workflow_id:
        q = q.where(Run.workflow_id == workflow_id)
    if status:
        q = q.where(Run.status == status)
    q = q.order_by(Run.created_at.desc())
    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db)):
    from app.services.runtime_service import RuntimeService
    run = await RuntimeService(db).trigger_run(
        workflow_id=payload.workflow_id,
        trigger_channel=payload.trigger_channel,
        trigger_payload=payload.trigger_payload,
    )
    return run


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _get_run_or_404(run_id, db)


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await _get_run_or_404(run_id, db)
    if run.status not in (RunStatus.pending, RunStatus.running):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot cancel run in status '{run.status}'",
        )
    run.status = RunStatus.cancelled
    await db.flush()
    await db.refresh(run)
    return run


@router.get("/{run_id}/timeline")
async def get_run_timeline(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return the full audit trail: run + steps + messages + tool_calls + token usage."""
    from app.services.runtime_service import RuntimeService
    timeline = await RuntimeService(db).get_run_timeline(run_id)
    if not timeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return timeline
