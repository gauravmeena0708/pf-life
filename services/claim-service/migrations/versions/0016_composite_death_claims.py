"""Link the two claims filed through a composite death form.

Revision ID: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "composite_ref" not in {c["name"] for c in sa.inspect(bind).get_columns("claims")}:
        op.add_column("claims", sa.Column("composite_ref", sa.String(40)))
    if "ix_claims_composite_ref" not in {i["name"] for i in sa.inspect(bind).get_indexes("claims")}:
        op.create_index("ix_claims_composite_ref", "claims", ["composite_ref"])


def downgrade() -> None:
    bind = op.get_bind()
    if "ix_claims_composite_ref" in {i["name"] for i in sa.inspect(bind).get_indexes("claims")}:
        op.drop_index("ix_claims_composite_ref", table_name="claims")
    if "composite_ref" in {c["name"] for c in sa.inspect(bind).get_columns("claims")}:
        op.drop_column("claims", "composite_ref")
