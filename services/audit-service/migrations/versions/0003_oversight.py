"""Security incidents, concurrent-audit alerts, office postings (Phase 2, slice 8e).

Revision ID: 0003
"""
from alembic import op

from app.infra.oversight_tables import oversight_metadata

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    oversight_metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    oversight_metadata.drop_all(bind=op.get_bind(), checkfirst=True)
