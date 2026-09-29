"""Establishment configuration (Phase 2, slice 6a): address, KYC, bank accounts, coverage; office postings, OLRE
scrutiny, change requests, Form 5A, branches, contractors.

Revision ID: 0006
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import branches, change_requests, contractors, office_staff, ownership_declarations, registration_scrutiny

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None
TABLES = (office_staff, registration_scrutiny, change_requests, ownership_declarations, branches, contractors)


def upgrade() -> None:
    for name in ("address", "kyc", "bank_accounts", "coverage"):
        op.add_column("establishments", sa.Column(name, sa.JSON()))
    for table in TABLES:
        table.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in reversed(TABLES):
        table.drop(bind=op.get_bind(), checkfirst=True)
    for name in ("coverage", "bank_accounts", "kyc", "address"):
        op.drop_column("establishments", name)
