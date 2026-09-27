"""Add synthetic establishment pincode for public search.

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("establishments", sa.Column("pincode", sa.String(6)))
    op.create_index("ix_establishments_pincode", "establishments", ["pincode"])


def downgrade() -> None:
    op.drop_index("ix_establishments_pincode", table_name="establishments")
    op.drop_column("establishments", "pincode")
