import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import Workflow, WorkflowStatus

router = APIRouter()


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    graph_json: dict = Field(default_factory=dict)
    cron_schedule: str | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph_json: dict | None = None
    status: WorkflowStatus | None = None
    cron_schedule: str | None = None


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    graph_json: dict
    status: WorkflowStatus
    cron_schedule: str | None
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}


async def _get_workflow_or_404(workflow_id: uuid.UUID, db: AsyncSession) -> Workflow:
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    wf = result.scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return wf


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(payload: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    wf = Workflow(**payload.model_dump())
    db.add(wf)
    await db.flush()
    await db.refresh(wf)
    return wf


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _get_workflow_or_404(workflow_id, db)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow_put(workflow_id: uuid.UUID, payload: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    """Full replacement update — used by the Canvas Save button (PUT)."""
    wf = await _get_workflow_or_404(workflow_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(wf, field, value)
    await db.flush()
    await db.refresh(wf)
    return wf


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow_patch(workflow_id: uuid.UUID, payload: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    """Partial update — kept for API consumers that prefer PATCH semantics."""
    wf = await _get_workflow_or_404(workflow_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(wf, field, value)
    await db.flush()
    await db.refresh(wf)
    return wf


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    wf = await _get_workflow_or_404(workflow_id, db)
    await db.delete(wf)


# ── Run trigger ────────────────────────────────────────────────────────────────

class WorkflowRunCreate(BaseModel):
    trigger_channel: str | None = "api"
    trigger_payload: dict | None = None
    message: str | None = None  # convenience: populates trigger_payload["message"]

    @model_validator(mode="after")
    def _merge_message(self) -> "WorkflowRunCreate":
        if self.message:
            payload = self.trigger_payload or {}
            payload["message"] = self.message
            self.trigger_payload = payload
        return self


class RunResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID | None
    status: Any
    trigger_channel: str | None
    trigger_payload: dict | None
    started_at: Any
    ended_at: Any
    created_at: Any

    model_config = {"from_attributes": True}


@router.post("/{workflow_id}/run", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def trigger_workflow_run(
    workflow_id: uuid.UUID,
    payload: WorkflowRunCreate,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new run for this workflow.  Returns immediately (run executes async)."""
    await _get_workflow_or_404(workflow_id, db)  # 404 guard
    from app.services.runtime_service import RuntimeService
    run = await RuntimeService(db).trigger_run(
        workflow_id=workflow_id,
        trigger_channel=payload.trigger_channel,
        trigger_payload=payload.trigger_payload or {},
    )
    return run
