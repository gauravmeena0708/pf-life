"""Freeze of an establishment (Phase 2, slice 5c).

Revision ID: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("establishments", sa.Column("frozen_at", sa.DateTime(timezone=True)))
    op.add_column("establishments", sa.Column("freeze", sa.JSON()))


def downgrade() -> None:
    op.drop_column("establishments", "freeze")
    op.drop_column("establishments", "frozen_at")
