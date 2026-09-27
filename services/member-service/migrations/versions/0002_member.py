"""Member-service tables.

Revision ID: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

IdType = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table("members",
        sa.Column("member_id", sa.String(40), primary_key=True),
        sa.Column("uan", sa.String(12), nullable=False, unique=True),
        sa.Column("subject", sa.String(80), unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("gender", sa.String(20), nullable=False),
        sa.Column("mobile_masked", sa.String(40), nullable=False),
        sa.Column("email_masked", sa.String(200), nullable=False),
        sa.Column("bank_ifsc", sa.String(20), nullable=False),
        sa.Column("bank_account_last4", sa.String(4), nullable=False),
        sa.Column("kyc", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("employments",
        sa.Column("account_link_id", sa.String(40), primary_key=True),
        sa.Column("member_id", sa.String(40), sa.ForeignKey("members.member_id"), nullable=False),
        sa.Column("establishment_id", sa.String(40), nullable=False),
        sa.Column("establishment_name", sa.String(200), nullable=False),
        sa.Column("date_of_joining", sa.Date, nullable=False),
        sa.Column("date_of_exit", sa.Date))
    op.create_table("notifications",
        sa.Column("id", IdType, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("recipient_subject", sa.String(80), nullable=False),
        sa.Column("template", sa.String(80), nullable=False),
        sa.Column("reference_id", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True)))
    op.create_index("ix_notifications_recipient_subject", "notifications", ["recipient_subject"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_subject", table_name="notifications")
    for table in ("notifications", "employments", "members"):
        op.drop_table(table)
