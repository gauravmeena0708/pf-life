"""Primary member ID and the Aadhaar-verified set in the claims projection (Phase 2, slice 7d).

Revision ID: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("accounts")}
    if "is_primary" not in existing:
        op.add_column("accounts", sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "set_key" not in existing:
        op.add_column("accounts", sa.Column("set_key", sa.String(200)))


def downgrade() -> None:
    op.drop_column("accounts", "set_key")
    op.drop_column("accounts", "is_primary")
