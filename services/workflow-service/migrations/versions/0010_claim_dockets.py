"""Claim Approval Dockets seen from claim-service (P2.5d).

Revision ID: 0010
"""
from alembic import op

from app.infra.tables import claim_dockets

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    claim_dockets.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    claim_dockets.drop(bind=op.get_bind(), checkfirst=True)
