"""Event-built read models owned by reporting-service."""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, MetaData, String, Table

metadata = MetaData()

grievance_facts = Table(
    "grievance_facts", metadata,
    Column("grievance_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("category", String(40), nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("tier", String(4), nullable=False),
    Column("escalations", Integer, nullable=False, server_default="0"),
    Column("resolved_at", DateTime(timezone=True)),
    Column("within_sla", Boolean),
)

claim_facts = Table(
    "claim_facts", metadata,
    Column("claim_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("form_type", String(40), nullable=False),
    Column("amount_paise", BigInteger, nullable=False),
    Column("route", String(12), nullable=False),
    Column("submitted_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
    Column("decision", String(20)),
    Column("settled_at", DateTime(timezone=True)),
    Column("returned_count", Integer, nullable=False, server_default="0"),
)

contribution_facts = Table(
    "contribution_facts", metadata,
    Column("filing_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False),
    Column("trrn", String(40), unique=True),
    Column("wage_month", String(7), index=True),
    Column("total_paise", BigInteger),
    Column("submitted_at", DateTime(timezone=True)),
    Column("paid_at", DateTime(timezone=True)),
    Column("posted_at", DateTime(timezone=True)),
)

event_freshness = Table(
    "event_freshness", metadata,
    Column("source", String(80), primary_key=True),
    Column("last_event_type", String(120), nullable=False),
    Column("last_event_at", DateTime(timezone=True), nullable=False),
    Column("events_seen", Integer, nullable=False, server_default="0"),
)
