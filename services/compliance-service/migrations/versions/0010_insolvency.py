"""P2.17: Insolvency watchlist, IBBI announcements, moratorium, resolution plans.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

from app.infra.tables import ecr_filings, insolvency_cases

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Check and add mca_status column on establishments if missing
    existing_cols = {c["name"] for c in insp.get_columns("establishments")}
    if "mca_status" not in existing_cols:
        op.add_column("establishments", sa.Column("mca_status", sa.String(40), nullable=True))

    # Guarded table creation
    for table in (ecr_filings, insolvency_cases):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (insolvency_cases, ecr_filings):
        table.drop(bind=bind, checkfirst=True)
    insp = sa.inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("establishments")}
    if "mca_status" in existing_cols:
        op.drop_column("establishments", "mca_status")
