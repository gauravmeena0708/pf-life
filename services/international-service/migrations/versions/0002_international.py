"""Agreements, Certificates of Coverage, the member projection, postings (Phase 2, slice 8c).

Revision ID: 0002
"""
from alembic import op

from app.infra.tables import metadata

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
