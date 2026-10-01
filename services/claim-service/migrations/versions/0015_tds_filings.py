"""Illustrative quarterly TDS filings and member name in the local account projection.

Revision ID: 0015
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import tds_filings

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "member_name" not in {c["name"] for c in sa.inspect(bind).get_columns("accounts")}:
        op.add_column("accounts", sa.Column("member_name", sa.String(120)))
    tds_filings.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    tds_filings.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("accounts", "member_name")
