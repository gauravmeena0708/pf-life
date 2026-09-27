"""Advisory risk flags per member (Journey D2).

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("risk_flags",
        sa.Column("signal_id", sa.String(40), primary_key=True),
        sa.Column("subject", sa.String(80), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False))


def downgrade() -> None:
    op.drop_table("risk_flags")
