"""Tables owned by compliance-service (Phase 2, slice 8a)."""
from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, MetaData, String, Table, Text, func

metadata = MetaData()

# Office postings and establishment names (synthetic seed) — jurisdiction, and the public defaulter list.
office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

establishments = Table(
    "establishments", metadata,
    Column("establishment_id", String(40), primary_key=True),
    Column("legal_name", String(200), nullable=False),
    Column("office_id", String(40), nullable=False),
)

# A compliance case: proceedings against an establishment for not filing, not paying, or damages.
compliance_cases = Table(
    "compliance_cases", metadata,
    Column("case_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("kind", String(30), nullable=False),               # NON_FILING | NON_PAYMENT | LATE_PAYMENT_DAMAGES | OTHER
    Column("wage_months", JSON, nullable=False),
    Column("amount_paise", BigInteger, nullable=False, server_default="0"),
    Column("state", String(20), nullable=False),              # OPEN | CLOSED
    Column("history", JSON, nullable=False),
    Column("opened_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# 14B / 7Q demands as contribution-service publishes them (DemandStateChanged.v1).
demands = Table(
    "demands", metadata,
    Column("demand_id", String(60), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("kind", String(20), nullable=False),
    Column("trrn", String(20)),
    Column("wage_month", String(7)),
    Column("amount_paise", BigInteger, nullable=False),
    Column("days_late", Integer, nullable=False, server_default="0"),
    Column("state", String(20), nullable=False),
    Column("working", Text),
)

# VISHWAS: settling disputed 14B damages (illustrative share in the rules).
vishwas_applications = Table(
    "vishwas_applications", metadata,
    Column("application_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("demand_ids", JSON, nullable=False),
    Column("damages_paise", BigInteger, nullable=False),
    Column("revised_paise", BigInteger),
    Column("state", String(20), nullable=False),              # SUBMITTED | APPROVED | REJECTED
    Column("submitted_by", String(80), nullable=False),
    Column("decided_by", String(80)),
    Column("decision_note", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
