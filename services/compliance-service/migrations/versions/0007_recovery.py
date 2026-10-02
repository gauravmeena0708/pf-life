"""Recovery under s.8B-8G (P2.11d).

Revision ID: 0007
"""
from alembic import op

from app.infra.tables import recovery_actions, recovery_cases

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (recovery_cases, recovery_actions):
        table.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (recovery_actions, recovery_cases):
        table.drop(bind=op.get_bind(), checkfirst=True)
