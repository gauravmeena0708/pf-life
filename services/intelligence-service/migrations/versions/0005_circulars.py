"""Circulars and notifications (Phase 2, slice 8d).

Revision ID: 0005
"""
from alembic import op

from app.infra.tables import circulars

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    circulars.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("circulars")
