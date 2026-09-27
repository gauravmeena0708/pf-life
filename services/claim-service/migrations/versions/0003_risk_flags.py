"""Advisory risk flags per member (Journey D2).

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _has(table: str, column: str | None = None) -> bool:
    """0002 creates tables from the current definitions, so on a fresh database later columns may already exist."""
    inspector = sa.inspect(op.get_bind())
    if column is None:
        return table in inspector.get_table_names()
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if _has("risk_flags"):
        return
    op.create_table("risk_flags",
        sa.Column("signal_id", sa.String(40), primary_key=True),
        sa.Column("subject", sa.String(80), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False))


def downgrade() -> None:
    op.drop_table("risk_flags")
