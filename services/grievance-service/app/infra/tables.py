"""Tables owned by grievance-service (created by migration 0002)."""
from sqlalchemy import JSON, Column, Date, DateTime, Integer, LargeBinary, MetaData, String, Table, Text, func

from app.infra.models import IdType

metadata = MetaData()

# Where a complainant's grievances go: the member's regional office and its zone (synthetic seed).
complainants = Table(
    "complainants", metadata,
    Column("subject", String(80), primary_key=True),
    Column("office_id", String(40), nullable=False),
    Column("zone_id", String(40), nullable=False),
)

# Officers and the office (RO) or zone (ZO) they act for.
office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

grievances = Table(
    "grievances", metadata,
    Column("grievance_id", String(40), primary_key=True),
    Column("complainant_subject", String(80), nullable=False, index=True),
    Column("category", String(40), nullable=False),
    Column("subject_line", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("linked_claim_id", String(40)),
    Column("office_id", String(40), nullable=False),     # the regional office that owns it
    Column("zone_id", String(40), nullable=False),
    Column("tier", String(4), nullable=False),           # RO | ZO | HO — who handles it now
    Column("state", String(30), nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("sla_due_at", DateTime(timezone=True), nullable=False),
    Column("resolution", Text),
    Column("resolved_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    # P2.8d: a grievance filed without a login keeps the contact only as a hash and the mobile's last four digits
    Column("source", String(10), nullable=False, server_default="MEMBER"),        # MEMBER | PUBLIC
    Column("complainant_type", String(30)),                                       # PENSIONER | EMPLOYER | MEMBER | OTHER (public)
    Column("public_name", String(120)),
    Column("mobile_hash", String(64)),
    Column("mobile_last4", String(4)),
    Column("reminders", Integer, nullable=False, server_default="0"),
    Column("last_reminded_at", DateTime(timezone=True)),
    Column("feedback", JSON),                                                     # {rating, satisfied, comment, at}
    Column("cpgrams_registration_no", String(80), unique=True),
)

rti_requests = Table(
    "rti_requests", metadata,
    Column("request_id", String(40), primary_key=True),
    Column("registration_no", String(100), nullable=False, unique=True),
    Column("registration_year", Integer, nullable=False),
    Column("office_id", String(40), nullable=False, index=True),
    Column("applicant_name", String(120), nullable=False),
    Column("received_on", Date, nullable=False),
    Column("mode", String(20), nullable=False),
    Column("subject", String(200), nullable=False),
    Column("information_sought", Text, nullable=False),
    Column("fee_paid", Integer, nullable=False),
    Column("bpl", Integer, nullable=False),
    Column("reply_due", Date, nullable=False),
    Column("state", String(20), nullable=False),
    Column("outcome", String(30)),
    Column("reply", Text),
    Column("exemption_section", String(20)),
    Column("transferred_to", String(200)),
    Column("replied_at", DateTime(timezone=True)),
    Column("late", Integer),
    Column("transfer_late", Integer),
)

# The conversation, status changes and evidence links, in order. Append-only.
grievance_entries = Table(
    "grievance_entries", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("grievance_id", String(40), nullable=False, index=True),
    Column("at", DateTime(timezone=True), server_default=func.now()),
    Column("kind", String(20), nullable=False),          # MESSAGE | STATUS | EVIDENCE | DOCUMENT
    Column("author_role", String(60), nullable=False),
    Column("state", String(30)),
    Column("body", Text, nullable=False),
    Column("evidence_refs", JSON),
)

grievance_documents = Table(
    "grievance_documents", metadata,
    Column("document_id", String(40), primary_key=True),
    Column("grievance_id", String(40), nullable=False, index=True),
    Column("filename", String(200), nullable=False),
    Column("content_type", String(80), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("content", LargeBinary, nullable=False),
    Column("uploaded_at", DateTime(timezone=True), server_default=func.now()),
)

# The offices a grievance can be transferred between (synthetic seed).
offices = Table(
    "offices", metadata,
    Column("office_id", String(40), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("zone_id", String(40), nullable=False),
)
