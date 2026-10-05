"""Event-built read models owned by reporting-service."""
from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, MetaData, String, Table, UniqueConstraint

metadata = MetaData()

service_standards = Table(
    "service_standards", metadata,
    Column("code", String(40), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("days", Integer, nullable=False),
    Column("basis", String(20), nullable=False),
    Column("source", String(160), nullable=False),
)

fund_positions = Table(
    "fund_positions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fund_manager", String(120), nullable=False),
    Column("fund", String(4), nullable=False),
    Column("as_of", Date, nullable=False),
    UniqueConstraint("fund_manager", "fund", "as_of"),
)

fund_holdings = Table(
    "fund_holdings", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("position_id", Integer, ForeignKey("fund_positions.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("isin", String(12), nullable=False),
    Column("asset_class", String(40), nullable=False),
    Column("book_value_paise", BigInteger, nullable=False),
    Column("market_value_paise", BigInteger, nullable=False),
)

office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

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
    Column("office_id", String(40), index=True),
    Column("form_type", String(40)),
    Column("amount_paise", BigInteger),
    Column("route", String(12)),
    Column("submitted_at", DateTime(timezone=True)),
    Column("decided_at", DateTime(timezone=True)),
    Column("decision", String(20)),
    Column("settled_at", DateTime(timezone=True)),
    Column("returned_count", Integer, nullable=False, server_default="0"),
)

contribution_facts = Table(
    "contribution_facts", metadata,
    Column("filing_id", String(40), primary_key=True),
    Column("establishment_id", String(40)),
    Column("trrn", String(40), unique=True),
    Column("wage_month", String(7), index=True),
    Column("total_paise", BigInteger),
    Column("submitted_at", DateTime(timezone=True)),
    Column("paid_at", DateTime(timezone=True)),
    Column("posted_at", DateTime(timezone=True)),
)

challan_payments = Table(
    "challan_payments", metadata,
    Column("trrn", String(40), primary_key=True),
    Column("paid_at", DateTime(timezone=True), nullable=False),
)


principal_employer_tags = Table(
    "principal_employer_tags", metadata,
    Column("filing_id", String(40), primary_key=True),
    Column("principal_establishment_id", String(40), primary_key=True),
    Column("work_order_ref", String(80), primary_key=True),
    Column("contractor_establishment_id", String(40), nullable=False, index=True),
    Column("wage_month", String(7), nullable=False),
    Column("members", Integer, nullable=False),
    Column("epf_wages_paise", BigInteger, nullable=False),
    Column("contribution_paise", BigInteger, nullable=False),
    Column("paid", Boolean, nullable=False, server_default="false"),
)

event_freshness = Table(
    "event_freshness", metadata,
    Column("source", String(80), primary_key=True),
    Column("last_event_type", String(120), nullable=False),
    Column("last_event_at", DateTime(timezone=True), nullable=False),
    Column("events_seen", Integer, nullable=False, server_default="0"),
)
