"""Cases also track grievances (Journey C): a case has either a claim or a grievance.

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
    op.alter_column("cases", "claim_id", existing_type=sa.String(40), nullable=True)
    if not _has("cases", "grievance_id"):
        op.add_column("cases", sa.Column("grievance_id", sa.String(40), unique=True))


def downgrade() -> None:
    op.drop_column("cases", "grievance_id")
    op.alter_column("cases", "claim_id", existing_type=sa.String(40), nullable=False)
