"""Claim attestation, bank switch and auto-transfer (Phase 2, slice 8b).

Revision ID: 0013
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import auto_transfers, member_bank_accounts

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "aadhaar_verified" not in {c["name"] for c in sa.inspect(bind).get_columns("accounts")}:
        op.add_column("accounts", sa.Column("aadhaar_verified", sa.Boolean(), nullable=False, server_default=sa.true()))
    member_bank_accounts.create(bind=bind, checkfirst=True)
    auto_transfers.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("auto_transfers")
    op.drop_table("member_bank_accounts")
    op.drop_column("accounts", "aadhaar_verified")
