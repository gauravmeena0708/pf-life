"""Tables owned by intelligence-service (created by migration 0002)."""
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text, func

from app.infra.models import IdType

metadata = MetaData()

# What the risk rules look at: security events only (never claim content or member data).
security_events = Table(
    "security_events", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("subject", String(80), nullable=False, index=True),
    Column("event_type", String(40), nullable=False),
    Column("device", String(64), nullable=False, index=True),
    Column("at", DateTime(timezone=True), nullable=False),
)

risk_signals = Table(
    "risk_signals", metadata,
    Column("signal_id", String(40), primary_key=True),
    Column("subject", String(80), nullable=False, index=True),
    Column("detection_type", String(60), nullable=False),
    Column("rule_version", String(40), nullable=False),
    Column("evidence_refs", JSON, nullable=False),
    Column("explanation", Text, nullable=False),
    Column("context", JSON, nullable=False),                  # facts shown to the reviewer that are NOT evidence
    Column("status", String(30), nullable=False),             # OPEN | NEEDS_MORE_EVIDENCE | CONFIRMED | BENIGN
    Column("review_note", Text),
    Column("reviewer_subject", String(80)),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
