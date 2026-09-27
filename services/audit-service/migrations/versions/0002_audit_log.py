"""Audit-service: the append-only, hash-chained audit log.

The table definition lives in app/infra/tables.py; this revision creates it and the triggers that
reject UPDATE and DELETE.

Revision ID: 0002
"""
from alembic import op

from app.infra.tables import install_append_only, metadata

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind())
    install_append_only(op.get_bind())


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only")
    metadata.drop_all(bind=op.get_bind())
