"""Synthetic office postings. Revision ID: 0004."""
from alembic import op

from app.infra.tables import office_staff

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    office_staff.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    office_staff.drop(bind=op.get_bind(), checkfirst=True)
