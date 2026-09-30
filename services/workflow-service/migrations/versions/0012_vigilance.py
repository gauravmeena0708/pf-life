"""Vigilance cases, their history and the CAIU's reviewed signals (Phase 2, slice 10a).

Revision ID: 0012
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import vigilance_actions, vigilance_cases, vigilance_signals

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in (vigilance_cases, vigilance_actions, vigilance_signals):
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    for name in ("vigilance_signals", "vigilance_actions", "vigilance_cases"):
        op.drop_table(name)
