"""International workers are members with different rules (Phase 2, slice 9a).

Revision ID: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "international" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("members")}:
        op.add_column("members", sa.Column("international", sa.JSON()))


def downgrade() -> None:
    op.drop_column("members", "international")
