"""PAST ACCUM VDR RECO: receipts of a trust's past accumulations reconciled (P2.14 completed).

Revision ID: 0022
"""
from alembic import op

from app.infra.models import PastAccumulationReconciliation

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    PastAccumulationReconciliation.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    PastAccumulationReconciliation.__table__.drop(bind=op.get_bind(), checkfirst=True)
