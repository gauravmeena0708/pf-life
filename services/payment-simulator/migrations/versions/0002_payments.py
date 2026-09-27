"""payment-simulator tables.

Revision ID: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("payables",
        sa.Column("trrn", sa.String(20), primary_key=True),
        sa.Column("establishment_id", sa.String(40), nullable=False),
        sa.Column("filing_id", sa.String(40), nullable=False),
        sa.Column("total_paise", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(20), nullable=False))
    op.create_table("payment_intents",
        sa.Column("payment_id", sa.String(40), primary_key=True),
        sa.Column("trrn", sa.String(20), nullable=False),
        sa.Column("amount_paise", sa.BigInteger, nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("scenario", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("bank_reference", sa.String(40)))
    op.create_index("ix_intents_pending", "payment_intents", ["status", "created_at"])
    op.create_table("bank_nonces",
        sa.Column("nonce", sa.String(64), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()))


def downgrade() -> None:
    for t in ("bank_nonces", "payment_intents", "payables"):
        op.drop_table(t)
