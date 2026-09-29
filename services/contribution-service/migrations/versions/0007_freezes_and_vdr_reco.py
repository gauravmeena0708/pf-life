"""Establishment freezes and the Annexure K VDR reconciliation (Phase 2, slice 5c).

Revision ID: 0007
"""
from alembic import op

from app.infra.models import AnnexureKVdrReco, EstablishmentFreeze

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    EstablishmentFreeze.__table__.create(bind=bind, checkfirst=True)
    AnnexureKVdrReco.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    AnnexureKVdrReco.__table__.drop(bind=op.get_bind(), checkfirst=True)
    EstablishmentFreeze.__table__.drop(bind=op.get_bind(), checkfirst=True)
