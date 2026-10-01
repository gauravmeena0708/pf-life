"""The EPS account of each member ID, so pension service adds up across a member's IDs (Phase 2, slice 9b).

Revision ID: 0008
"""
from alembic import op

from app.infra.tables import eps_accounts

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    eps_accounts.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("eps_accounts")
