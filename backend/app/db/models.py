import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float,
    DateTime, ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
import enum


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────────

class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class StepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class WorkflowStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


# ── Domain tables ──────────────────────────────────────────────────────────────

class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    role = Column(String(128), nullable=True)
    system_prompt = Column(Text, nullable=False)
    tools_enabled = Column("tools", JSON, nullable=False, default=list)
    model_provider = Column("provider", String(64), nullable=False, default="google")
    model_name = Column("model", String(128), nullable=False, default="gemini-1.5-flash")
    temperature = Column(Float, nullable=False, default=0.1)
    memory_enabled = Column(Boolean, nullable=False, default=False)
    max_iterations = Column(Integer, nullable=False, default=10)
    max_cost_usd = Column(Float, nullable=False, default=1.0)
    channel_bindings = Column(JSON, nullable=True, default=None)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    run_steps = relationship("RunStep", back_populates="agent")


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    graph_json = Column(JSON, nullable=False, default=dict)
    status = Column(SAEnum(WorkflowStatus), nullable=False, default=WorkflowStatus.draft)
    cron_schedule = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    runs = relationship("Run", back_populates="workflow")


class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True)
    status = Column(SAEnum(RunStatus), nullable=False, default=RunStatus.pending)
    trigger_channel = Column(String(64), nullable=True)
    trigger_payload = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    error_message = Column(Text, nullable=True)
    total_cost_usd = Column(Float, nullable=True)
    final_response = Column(Text, nullable=True)

    workflow = relationship("Workflow", back_populates="runs")
    steps = relationship("RunStep", back_populates="run", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="run", cascade="all, delete-orphan")
    token_usages = relationship("TokenUsage", back_populates="run", cascade="all, delete-orphan")


class RunStep(Base):
    __tablename__ = "run_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    status = Column(SAEnum(StepStatus), nullable=False, default=StepStatus.pending)
    input = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("Run", back_populates="steps")
    agent = relationship("Agent", back_populates="run_steps")
    tool_calls = relationship("ToolCall", back_populates="run_step", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    role = Column(SAEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("Run", back_populates="messages")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_step_id = Column(UUID(as_uuid=True), ForeignKey("run_steps.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(128), nullable=False)
    input = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run_step = relationship("RunStep", back_populates="tool_calls")


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Float, nullable=True, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("Run", back_populates="token_usages")


# ── Routing rules table ────────────────────────────────────────────────────────

class RoutingRule(Base):
    """
    Keyword-based routing table for Telegram messages.
    Rules are evaluated in descending priority order; first keyword match wins.
    """
    __tablename__ = "routing_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keywords = Column(ARRAY(Text), nullable=False, default=list)
    workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
    )
    priority = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Eager-loadable join to Workflow (forward ref — no backref needed on Workflow)
    workflow = relationship("Workflow", foreign_keys=[workflow_id])


# ── Mock data tables ───────────────────────────────────────────────────────────

class MockTransaction(Base):
    __tablename__ = "mock_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(String(64), nullable=False, unique=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    status = Column(String(32), nullable=False)
    psp = Column(String(64), nullable=False)
    failure_reason = Column(String(255), nullable=True)
    extra = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MockPspStatus(Base):
    __tablename__ = "mock_psp_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    psp_name = Column(String(64), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default="operational")
    latency_ms = Column(Integer, nullable=False, default=200)
    error_rate = Column(Float, nullable=False, default=0.01)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MockRoutingLog(Base):
    __tablename__ = "mock_routing_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(String(64), nullable=False)
    from_psp = Column(String(64), nullable=True)
    to_psp = Column(String(64), nullable=False)
    reason = Column(String(255), nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
