"""runs — add total_cost_usd, error_message

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-24 00:02:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("error_message", sa.Text, nullable=True))
    op.add_column("runs", sa.Column("total_cost_usd", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "total_cost_usd")
    op.drop_column("runs", "error_message")
