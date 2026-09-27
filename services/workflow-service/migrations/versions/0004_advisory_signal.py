"""Cases show an open advisory risk signal to the officer (Journey D2).

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("advisory_signal_id", sa.String(40)))


def downgrade() -> None:
    op.drop_column("cases", "advisory_signal_id")
