"""agents — add channel_bindings JSON column

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-26 00:06:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("channel_bindings", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "channel_bindings")
