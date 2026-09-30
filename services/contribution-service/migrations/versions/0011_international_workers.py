"""International workers contribute on full wages (Phase 2, slice 9a).

Revision ID: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "international_worker" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("establishment_members")}:
        op.add_column("establishment_members", sa.Column("international_worker", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("establishment_members", "international_worker")
