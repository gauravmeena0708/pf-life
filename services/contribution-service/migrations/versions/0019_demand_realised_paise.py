"""Add realised_paise column to demands.

Revision ID: 0019
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "demands" in set(inspector.get_table_names()):
        columns = {c["name"] for c in inspector.get_columns("demands")}
        if "realised_paise" not in columns:
            op.add_column("demands", sa.Column("realised_paise", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "demands" in set(inspector.get_table_names()):
        columns = {c["name"] for c in inspector.get_columns("demands")}
        if "realised_paise" in columns:
            op.drop_column("demands", "realised_paise")
