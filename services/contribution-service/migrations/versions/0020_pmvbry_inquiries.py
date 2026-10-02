"""Inquiries that withhold PMVBRY Part B (P2.11d).

Revision ID: 0020
"""
from alembic import op

from app.infra.models import PmvbryInquiry

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    PmvbryInquiry.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    PmvbryInquiry.__table__.drop(bind=op.get_bind(), checkfirst=True)
