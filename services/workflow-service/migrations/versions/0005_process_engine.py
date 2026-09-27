"""Process engine (ADR-0005): engine cases carry a process name and subject; subjects map to offices.

Revision ID: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _has(table: str, column: str | None = None) -> bool:
    """0002 creates tables from the current definitions, so on a fresh database later columns may already exist."""
    inspector = sa.inspect(op.get_bind())
    if column is None:
        return table in inspector.get_table_names()
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has("cases", "process"):
        op.add_column("cases", sa.Column("process", sa.String(60)))
        op.add_column("cases", sa.Column("subject_ref", sa.String(40), index=True))
    if _has("subject_offices"):
        return
    op.create_table("subject_offices",
        sa.Column("subject_ref", sa.String(40), primary_key=True),
        sa.Column("office_id", sa.String(40), nullable=False),
        sa.Column("zone_id", sa.String(40)))


def downgrade() -> None:
    op.drop_table("subject_offices")
    op.drop_column("cases", "subject_ref")
    op.drop_column("cases", "process")
