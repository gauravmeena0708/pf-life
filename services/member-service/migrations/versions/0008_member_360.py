"""Office postings and the office of each employment, for the member 360 view.

Revision ID: 0008
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import office_staff

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "office_id" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("employments")}:
        op.add_column("employments", sa.Column("office_id", sa.String(40)))
    office_staff.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    office_staff.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("employments", "office_id")
