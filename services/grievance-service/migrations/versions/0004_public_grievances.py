"""Grievances without a login, reminders, feedback, office transfers (Phase 2, slice 8d).

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import offices

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

COLUMNS = [sa.Column("source", sa.String(10), nullable=False, server_default="MEMBER"), sa.Column("complainant_type", sa.String(30)),
           sa.Column("public_name", sa.String(120)), sa.Column("mobile_hash", sa.String(64)), sa.Column("mobile_last4", sa.String(4)),
           sa.Column("reminders", sa.Integer(), nullable=False, server_default="0"),
           sa.Column("last_reminded_at", sa.DateTime(timezone=True)), sa.Column("feedback", sa.JSON())]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("grievances")}
    for column in COLUMNS:
        if column.name not in existing:
            op.add_column("grievances", column)
    offices.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("offices")
    for column in reversed(COLUMNS):
        op.drop_column("grievances", column.name)
