"""Published rule sets received from platform-service (PolicyPublished.v1).

Revision ID: 0003
"""
from alembic import op

from epfo_persistence.policy import policy_metadata, policy_rules

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    policy_metadata.create_all(bind=op.get_bind(), tables=[policy_rules])


def downgrade() -> None:
    policy_rules.drop(bind=op.get_bind(), checkfirst=True)
