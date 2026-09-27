"""Frozen accounts (AccountFrozen.v1 / AccountDefrozen.v1): claims and payments stop while frozen.

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("accounts")}
    if "uan" not in columns:           # 0002 builds from the current definitions, so a fresh database has them
        op.add_column("accounts", sa.Column("uan", sa.String(12), index=True))
        op.add_column("accounts", sa.Column("frozen", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("accounts", "frozen")
    op.drop_column("accounts", "uan")
