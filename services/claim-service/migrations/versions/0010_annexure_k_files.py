"""Annexure K files between field offices (Phase 2, slice 5c).

Revision ID: 0010
"""
from alembic import op

from app.infra.tables import annexure_k_files

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    annexure_k_files.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    annexure_k_files.drop(bind=op.get_bind(), checkfirst=True)
