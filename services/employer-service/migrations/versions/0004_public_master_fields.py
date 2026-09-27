"""Add non-sensitive public directory fields based on a master-data shape.

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("establishments", sa.Column("city", sa.String(80)))
    op.add_column("establishments", sa.Column("district", sa.String(80)))
    op.add_column("establishments", sa.Column("coverage_date", sa.Date()))
    op.add_column("establishments", sa.Column("establishment_type", sa.String(80)))
    op.add_column("establishments", sa.Column("industry_group", sa.String(120)))
    op.add_column("establishments", sa.Column("exemption_status", sa.String(30)))
    op.create_index("ix_establishments_district", "establishments", ["district"])


def downgrade() -> None:
    op.drop_index("ix_establishments_district", table_name="establishments")
    for name in ("exemption_status", "industry_group", "establishment_type", "coverage_date", "district", "city"):
        op.drop_column("establishments", name)
