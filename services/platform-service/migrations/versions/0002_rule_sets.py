"""Policy administration: versioned rule sets.

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
