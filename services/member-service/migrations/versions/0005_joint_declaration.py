"""Joint Declaration corrections: extra profile fields and the change history.

Revision ID: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("profile_extra", sa.JSON))
    op.create_table("member_changes",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(40), nullable=False, index=True),
        sa.Column("member_id", sa.String(40), sa.ForeignKey("members.member_id"), nullable=False),
        sa.Column("parameter", sa.String(40), nullable=False),
        sa.Column("old_value", sa.String(200)),
        sa.Column("new_value", sa.String(200), nullable=False),
        sa.Column("approved_by", sa.String(80), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_table("member_changes")
    op.drop_column("members", "profile_extra")
