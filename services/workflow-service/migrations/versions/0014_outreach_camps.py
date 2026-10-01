"""Nidhi Aapke Nikat camps and assisted requests (Phase 2, slice 12f).

Revision ID: 0014
"""
from alembic import op

from app.infra.tables import camp_requests, outreach_camps

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    outreach_camps.create(bind, checkfirst=True)
    camp_requests.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    camp_requests.drop(bind, checkfirst=True)
    outreach_camps.drop(bind, checkfirst=True)
