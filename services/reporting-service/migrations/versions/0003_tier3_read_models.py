"""Tier-3 event projections. Revision ID: 0003."""
from alembic import op

from app.infra.tables import claim_facts, contribution_facts, event_freshness

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = (claim_facts, contribution_facts, event_freshness)


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind=bind, checkfirst=True)
