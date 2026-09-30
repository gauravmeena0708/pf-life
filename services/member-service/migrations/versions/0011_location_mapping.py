"""Member location mapping (Phase 2, slice 8e).

Revision ID: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "location" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("employments")}:
        op.add_column("employments", sa.Column("location", sa.JSON()))


def downgrade() -> None:
    op.drop_column("employments", "location")
