"""Claim documents, the Claim Authorization Document (CAD) and payment scrolls.

Revision ID: 0008
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import cads, claim_documents, payment_scrolls

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "interest_paise" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("accounts")}:
        op.add_column("accounts", sa.Column("interest_paise", sa.BigInteger, nullable=False, server_default="0"))
    for table in (claim_documents, cads, payment_scrolls):
        table.create(bind=op.get_bind(), checkfirst=True)      # 0002 may already have built them


def downgrade() -> None:
    for table in (payment_scrolls, cads, claim_documents):
        table.drop(bind=op.get_bind(), checkfirst=True)
