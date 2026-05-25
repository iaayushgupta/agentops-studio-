"""agents — add role, memory_enabled, max_iterations, max_cost_usd

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-24 00:01:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("role", sa.String(128), nullable=True))
    op.add_column("agents", sa.Column("memory_enabled", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("agents", sa.Column("max_iterations", sa.Integer, nullable=False, server_default="10"))
    op.add_column("agents", sa.Column("max_cost_usd", sa.Float, nullable=False, server_default="1.0"))


def downgrade() -> None:
    op.drop_column("agents", "max_cost_usd")
    op.drop_column("agents", "max_iterations")
    op.drop_column("agents", "memory_enabled")
    op.drop_column("agents", "role")
