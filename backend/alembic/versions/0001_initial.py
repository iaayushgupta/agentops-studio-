"""initial schema — all 10 tables

Revision ID: 0001
Revises:
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # agents
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("tools", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("provider", sa.String(64), nullable=False, server_default="google"),
        sa.Column("model", sa.String(128), nullable=False, server_default="gemini-1.5-flash"),
        sa.Column("temperature", sa.Float, nullable=False, server_default="0.1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # workflows
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("graph_json", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", name="workflowstatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("cron_schedule", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # runs
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", "cancelled", name="runstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("trigger_channel", sa.String(64), nullable=True),
        sa.Column("trigger_payload", postgresql.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # run_steps
    op.create_table(
        "run_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="stepstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("input", postgresql.JSON, nullable=True),
        sa.Column("output", postgresql.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )

    # messages
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "system", "tool", name="messagerole"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # tool_calls
    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("run_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("input", postgresql.JSON, nullable=True),
        sa.Column("output", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # token_usage
    op.create_table(
        "token_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # mock_transactions
    op.create_table(
        "mock_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", sa.String(64), nullable=False, unique=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("psp", sa.String(64), nullable=False),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        sa.Column("metadata", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # mock_psp_status
    op.create_table(
        "mock_psp_status",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("psp_name", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="operational"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="200"),
        sa.Column("error_rate", sa.Float, nullable=False, server_default="0.01"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # mock_routing_logs
    op.create_table(
        "mock_routing_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("from_psp", sa.String(64), nullable=True),
        sa.Column("to_psp", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Indexes
    op.create_index("ix_runs_workflow_id", "runs", ["workflow_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])
    op.create_index("ix_messages_run_id", "messages", ["run_id"])
    op.create_index("ix_tool_calls_run_step_id", "tool_calls", ["run_step_id"])
    op.create_index("ix_token_usage_run_id", "token_usage", ["run_id"])
    op.create_index("ix_mock_transactions_transaction_id", "mock_transactions", ["transaction_id"])
    op.create_index("ix_mock_routing_logs_transaction_id", "mock_routing_logs", ["transaction_id"])


def downgrade() -> None:
    op.drop_table("mock_routing_logs")
    op.drop_table("mock_psp_status")
    op.drop_table("mock_transactions")
    op.drop_table("token_usage")
    op.drop_table("tool_calls")
    op.drop_table("messages")
    op.drop_table("run_steps")
    op.drop_table("runs")
    op.drop_table("workflows")
    op.drop_table("agents")
    op.execute("DROP TYPE IF EXISTS workflowstatus")
    op.execute("DROP TYPE IF EXISTS runstatus")
    op.execute("DROP TYPE IF EXISTS stepstatus")
    op.execute("DROP TYPE IF EXISTS messagerole")
