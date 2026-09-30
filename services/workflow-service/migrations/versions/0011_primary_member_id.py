"""Primary member ID in the member-account projection (Phase 2, slice 7d).

Revision ID: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "is_primary" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("member_accounts")}:
        op.add_column("member_accounts", sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("member_accounts", "is_primary")
