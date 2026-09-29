"""DSC / e-sign registrations of signatories with their request and revoke letters (Phase 2, slice 6b).

Revision ID: 0007
"""
from alembic import op

from app.infra.tables import signature_registrations

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    signature_registrations.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    signature_registrations.drop(bind=op.get_bind(), checkfirst=True)
