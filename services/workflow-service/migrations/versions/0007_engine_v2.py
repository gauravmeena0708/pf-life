"""Engine v2: case data, and subjects that know their member and establishment (Joint Declaration).

Revision ID: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _has(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has("cases", "data"):
        op.add_column("cases", sa.Column("data", sa.JSON))
    if not _has("subject_offices", "member_subject"):
        op.add_column("subject_offices", sa.Column("member_subject", sa.String(80), index=True))
        op.add_column("subject_offices", sa.Column("establishment_id", sa.String(40)))


def downgrade() -> None:
    op.drop_column("subject_offices", "establishment_id")
    op.drop_column("subject_offices", "member_subject")
    op.drop_column("cases", "data")
