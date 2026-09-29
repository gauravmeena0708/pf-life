"""Ledger locks, signed case documents and who viewed them (Phase 2, slice 5c).

Revision ID: 0009
"""
from alembic import op

from app.infra.tables import case_documents, document_views, ledger_locks

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (ledger_locks, case_documents, document_views):
        table.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (document_views, case_documents, ledger_locks):
        table.drop(bind=op.get_bind(), checkfirst=True)
