"""Tables owned by payment-simulator (the MOCK bank). Never real money."""
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, func
from sqlalchemy import BigInteger

metadata = MetaData()
Money = BigInteger().with_variant(Integer, "sqlite")

payables = Table(  # learnt from contribution-service.ECRSubmitted.v1
    "payables", metadata,
    Column("trrn", String(20), primary_key=True),
    Column("establishment_id", String(40), nullable=False),
    Column("filing_id", String(40), nullable=False),
    Column("total_paise", Money, nullable=False),
    Column("status", String(20), nullable=False),          # DUE | PENDING | PAID | FAILED
)
payment_intents = Table(
    "payment_intents", metadata,
    Column("payment_id", String(40), primary_key=True),
    Column("trrn", String(20)),                             # set for challans
    Column("purpose", String(20), nullable=False, server_default="CHALLAN"),   # CHALLAN | CLAIM_SETTLEMENT
    Column("reference_id", String(40)),                     # claim ID for claim settlements
    Column("amount_paise", Money, nullable=False),
    Column("channel", String(20), nullable=False),
    Column("scenario", String(20), nullable=False),        # SUCCESS | RETURN (demo switch)
    Column("status", String(20), nullable=False),          # PENDING | CONFIRMED | RETURNED
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("settled_at", DateTime(timezone=True)),
    Column("bank_reference", String(40)),
)
bank_nonces = Table(  # replay protection for signed bank callbacks
    "bank_nonces", metadata,
    Column("nonce", String(64), primary_key=True),
    Column("seen_at", DateTime(timezone=True), server_default=func.now()),
)
