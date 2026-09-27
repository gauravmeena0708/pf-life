"""Cases show an open advisory risk signal to the officer (Journey D2).

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _has(table: str, column: str | None = None) -> bool:
    """0002 creates tables from the current definitions, so on a fresh database later columns may already exist."""
    inspector = sa.inspect(op.get_bind())
    if column is None:
        return table in inspector.get_table_names()
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has("cases", "advisory_signal_id"):
        op.add_column("cases", sa.Column("advisory_signal_id", sa.String(40)))


def downgrade() -> None:
    op.drop_column("cases", "advisory_signal_id")
