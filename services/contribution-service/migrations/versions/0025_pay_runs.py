"""Pay runs for payroll provider integration (P2.22).

Revision ID: 0025
"""
from alembic import op

from app.infra.models import PayRun

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    PayRun.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    PayRun.__table__.drop(bind=op.get_bind(), checkfirst=True)
