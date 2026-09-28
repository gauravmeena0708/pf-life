"""Pensions in payment, revisions under a changed formula, mock CPPS payments, and published rule sets.

Revision ID: 0002
"""
from alembic import op

from app.infra.tables import metadata
from epfo_persistence.policy import policy_metadata, policy_rules

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), checkfirst=True)
    policy_metadata.create_all(bind=op.get_bind(), tables=[policy_rules], checkfirst=True)


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind())
    policy_rules.drop(bind=op.get_bind(), checkfirst=True)
