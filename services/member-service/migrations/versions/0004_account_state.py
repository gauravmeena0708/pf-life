"""Account state from the member_freeze process (ADR-0005).

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("account_state", sa.String(20), nullable=False, server_default="ACTIVE"))


def downgrade() -> None:
    op.drop_column("members", "account_state")
