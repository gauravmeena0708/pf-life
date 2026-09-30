"""Primary member ID and the Aadhaar-verified set (Phase 2, slice 7d).

Revision ID: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("members")}
    if "aadhaar_ref" not in existing:
        op.add_column("members", sa.Column("aadhaar_ref", sa.String(64)))
        op.create_index("ix_members_aadhaar_ref", "members", ["aadhaar_ref"])
    if "primary_account_link_id" not in existing:
        op.add_column("members", sa.Column("primary_account_link_id", sa.String(40)))


def downgrade() -> None:
    op.drop_column("members", "primary_account_link_id")
    op.drop_index("ix_members_aadhaar_ref", table_name="members")
    op.drop_column("members", "aadhaar_ref")
