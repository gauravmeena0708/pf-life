"""payroll_providers table.

Revision ID: 0011
"""
from alembic import op

from app.infra.tables import payroll_providers

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    payroll_providers.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    payroll_providers.drop(bind=op.get_bind(), checkfirst=True)
