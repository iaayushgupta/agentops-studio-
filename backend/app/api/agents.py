import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import Agent

router = APIRouter()

# ── Schemas ────────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    role: str | None = None
    system_prompt: str = Field(..., min_length=1)
    tools_enabled: list[str] = Field(default_factory=list)
    model_provider: str = "google"
    model_name: str = "gemini-1.5-flash"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    memory_enabled: bool = False
    max_iterations: int = Field(default=10, ge=1, le=100)
    max_cost_usd: float = Field(default=1.0, ge=0.0)
    channel_bindings: dict | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    role: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    tools_enabled: list[str] | None = None
    model_provider: str | None = None
    model_name: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    memory_enabled: bool | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=100)
    max_cost_usd: float | None = Field(default=None, ge=0.0)
    channel_bindings: dict | None = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    role: str | None
    system_prompt: str
    tools_enabled: list[Any]
    model_provider: str
    model_name: str
    temperature: float
    memory_enabled: bool
    max_iterations: int
    max_cost_usd: float
    channel_bindings: dict | None = None
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_agent_or_404(agent_id: uuid.UUID, db: AsyncSession) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentResponse])
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    result = await db.execute(select(Agent).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    existing = await db.execute(select(Agent).where(Agent.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Agent with name '{payload.name}' already exists",
        )
    agent = Agent(**payload.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    return await _get_agent_or_404(agent_id, db)


@router.put("/{agent_id}", response_model=AgentResponse)
@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    agent = await _get_agent_or_404(agent_id, db)
    updates = payload.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] != agent.name:
        existing = await db.execute(select(Agent).where(Agent.name == updates["name"]))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Agent with name '{updates['name']}' already exists",
            )

    for field, value in updates.items():
        setattr(agent, field, value)

    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    agent = await _get_agent_or_404(agent_id, db)
    await db.delete(agent)
