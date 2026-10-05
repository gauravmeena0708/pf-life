"""Order-safe case copies: event timestamp guard so older events never overwrite newer state.

Revision ID: 0015
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _has(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has("cases", "source_at"):
        op.add_column("cases", sa.Column("source_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("cases", "source_at")
