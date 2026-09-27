"""Member security: contact history, security reports and reviewed account recovery (Journey D).

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("contact_history",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("member_id", sa.String(40), sa.ForeignKey("members.member_id"), nullable=False, index=True),
        sa.Column("mobile_masked", sa.String(40), nullable=False),
        sa.Column("email_masked", sa.String(200), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("security_reports",
        sa.Column("report_id", sa.String(40), primary_key=True),
        sa.Column("subject", sa.String(80), nullable=False, index=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("recovery_requests",
        sa.Column("request_id", sa.String(40), primary_key=True),
        sa.Column("member_id", sa.String(40), sa.ForeignKey("members.member_id"), nullable=False),
        sa.Column("subject", sa.String(80), nullable=False, index=True),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("restore_to", sa.JSON, nullable=False),
        sa.Column("reviewer_subject", sa.String(80)),
        sa.Column("decision_note", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_table("recovery_requests")
    op.drop_table("security_reports")
    op.drop_table("contact_history")
