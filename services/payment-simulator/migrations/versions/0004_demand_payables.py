"""Demands payable directly (Phase 2, slice 8a).

Revision ID: 0004
"""
from alembic import op

from app.infra.tables import demand_payables

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    demand_payables.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    demand_payables.drop(bind=op.get_bind(), checkfirst=True)
