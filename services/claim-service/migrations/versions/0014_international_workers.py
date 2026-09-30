"""International workers in the claims projection (Phase 2, slice 9a).

Revision ID: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

COLUMNS = [sa.Column("international_worker", sa.Boolean(), nullable=False, server_default=sa.false()),
           sa.Column("nationality", sa.String(60)), sa.Column("date_of_birth", sa.Date())]


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("accounts")}
    for column in COLUMNS:
        if column.name not in existing:
            op.add_column("accounts", column)


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("accounts", column.name)
