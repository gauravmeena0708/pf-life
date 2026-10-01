"""Officers' postings, so office routes scope to the officer's office (Phase 2, slice 9d).

Revision ID: 0016
"""
from alembic import op

from app.infra.models import OfficeStaff

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    OfficeStaff.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    OfficeStaff.__table__.drop(bind=op.get_bind(), checkfirst=True)
