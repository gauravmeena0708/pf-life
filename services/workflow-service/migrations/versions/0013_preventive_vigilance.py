"""Posting dates for tenure on sensitive posts; vigilance clearances (Phase 2, slice 10b).

Revision ID: 0013
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import vigilance_clearances

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "posted_since" not in {c["name"] for c in sa.inspect(bind).get_columns("office_staff")}:
        op.add_column("office_staff", sa.Column("posted_since", sa.Date()))
    vigilance_clearances.create(bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("vigilance_clearances")
    op.drop_column("office_staff", "posted_since")
