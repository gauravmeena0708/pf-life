"""Fund position snapshots and local policy rules. Revision ID: 0006."""
from alembic import op

from app.infra.tables import fund_holdings, fund_positions
from epfo_persistence.policy import policy_rules

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    fund_positions.create(bind=bind, checkfirst=True)
    fund_holdings.create(bind=bind, checkfirst=True)
    policy_rules.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    policy_rules.drop(bind=bind, checkfirst=True)
    fund_holdings.drop(bind=bind, checkfirst=True)
    fund_positions.drop(bind=bind, checkfirst=True)
