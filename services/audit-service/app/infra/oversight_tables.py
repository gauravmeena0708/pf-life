"""Tables for oversight work (Phase 2, slice 8e), apart from the append-only audit log: security incidents and their
CERT-In reporting, concurrent-audit alerts to offices and their replies, and office postings (who may reply)."""
from sqlalchemy import JSON, Column, Date, DateTime, Integer, MetaData, String, Table, Text, func

oversight_metadata = MetaData()

offices = Table(
    "offices", oversight_metadata,
    Column("office_id", String(40), primary_key=True),
    Column("zone_id", String(40), nullable=False, index=True),
)

office_staff = Table(
    "office_staff", oversight_metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

security_incidents = Table(
    "security_incidents", oversight_metadata,
    Column("incident_id", String(40), primary_key=True),
    Column("title", String(200), nullable=False),
    Column("category", String(40), nullable=False),
    Column("severity", String(10), nullable=False),
    Column("detected_at", DateTime(timezone=True), nullable=False),
    Column("description", Text, nullable=False),
    Column("affected_systems", JSON, nullable=False),
    Column("related_event_ids", JSON, nullable=False),
    Column("cert_in", JSON),                      # {required, due_by, reported_at, acknowledgement (mock)} or null
    Column("recorded_by", String(80), nullable=False),
    Column("recorded_at", DateTime(timezone=True), server_default=func.now()),
)

concurrent_alerts = Table(
    "concurrent_alerts", oversight_metadata,
    Column("alert_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("zone_id", String(40), nullable=False),
    Column("reference", String(80), nullable=False),               # a claim, transfer, journal … or an audit event ID
    Column("event_id", String(36)),
    Column("flags", JSON, nullable=False),
    Column("finding", Text, nullable=False),
    Column("state", String(20), nullable=False),                   # OPEN | REPLIED | CLOSED
    Column("due_by", DateTime(timezone=True), nullable=False),
    Column("raised_by", String(80), nullable=False),
    Column("raised_at", DateTime(timezone=True), server_default=func.now()),
    Column("reply", JSON),                                         # {reply, action_taken, by, at}
)

internal_reports = Table(
    "internal_reports", oversight_metadata,
    Column("report_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("zone_id", String(40), nullable=False),
    Column("period_from", Date, nullable=False),
    Column("period_to", Date, nullable=False),
    Column("scope", Text, nullable=False),
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

internal_paras = Table(
    "internal_paras", oversight_metadata,
    Column("para_id", String(40), primary_key=True),
    Column("report_id", String(40), nullable=False, index=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("zone_id", String(40), nullable=False),
    Column("category", String(30), nullable=False),
    Column("observation", Text, nullable=False),
    Column("amount_at_risk_paise", Integer, nullable=False),
    Column("references", JSON, nullable=False),
    Column("recommendation", Text, nullable=False),
    Column("reply_due", Date, nullable=False),
    Column("state", String(20), nullable=False),
    Column("replies", JSON, nullable=False),
    Column("decisions", JSON, nullable=False),
    Column("raised_at", DateTime(timezone=True), server_default=func.now()),
)

privacy_requests = Table(
    "privacy_requests", oversight_metadata,
    Column("request_id", String(40), primary_key=True),
    Column("member_subject", String(80), nullable=False, index=True),
    Column("kind", String(20), nullable=False),
    Column("details", Text, nullable=False),
    Column("state", String(20), nullable=False),
    Column("due_on", Date, nullable=False),
    Column("answer", Text),
    Column("legal_basis", Text),
    Column("decided_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
