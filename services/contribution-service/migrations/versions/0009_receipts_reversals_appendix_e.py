"""Ledger work (Phase 2, slice 7b): receipts outside the challan flow (VDR), transfer recredits, Appendix E.

Revision ID: 0009
"""
import sqlalchemy as sa
from alembic import op

from app.infra.models import LedgerAdjustment, VdrEntry

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0006 builds transfer_postings from the current model on a fresh database, so the column may already exist
    if "recredit_journal_id" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("transfer_postings")}:
        op.add_column("transfer_postings", sa.Column("recredit_journal_id", sa.String(36)))
    VdrEntry.__table__.create(bind=op.get_bind(), checkfirst=True)
    LedgerAdjustment.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    LedgerAdjustment.__table__.drop(bind=op.get_bind(), checkfirst=True)
    VdrEntry.__table__.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("transfer_postings", "recredit_journal_id")
