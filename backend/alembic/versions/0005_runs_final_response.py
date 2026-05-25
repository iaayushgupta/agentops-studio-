"""runs — add final_response column

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-24 00:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("final_response", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "final_response")
