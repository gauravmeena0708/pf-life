"""Workflow-service tables: offices, office postings, cases and the case action log.

The table definitions live in app/infra/tables.py; this revision creates exactly those tables.

Revision ID: 0002
"""
from alembic import op

from app.infra.tables import metadata

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind())
