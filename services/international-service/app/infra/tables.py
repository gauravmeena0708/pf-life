"""Tables owned by international-service (Phase 2, slice 8c)."""
from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, DateTime, Integer, MetaData, String, Table, Text, false, func

metadata = MetaData()

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

# The member IDs this service needs (seeded, then MemberRegistered.v1 / MemberExitMarked.v1): who works where, and
# for a foreign national employed in India, the nationality and a masked passport number.
members = Table(
    "members", metadata,
    Column("account_link_id", String(40), primary_key=True),
    Column("uan", String(12), nullable=False, index=True),
    Column("subject", String(80), index=True),
    Column("name", String(200), nullable=False),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("date_of_joining", Date, nullable=False),
    Column("date_of_exit", Date),
    Column("international_worker", Boolean, nullable=False, server_default=false()),
    Column("nationality", String(60)),
    Column("passport_masked", String(20)),
)

# Social-security agreements (synthetic catalogue; the countries are India's agreement partners, the terms here are
# illustrative, not the agreements' text).
agreements = Table(
    "agreements", metadata,
    Column("country", String(60), primary_key=True),
    Column("code", String(3), nullable=False),
    Column("in_force_from", Date, nullable=False),
    Column("max_posting_months", Integer, nullable=False),
    Column("max_extension_months", Integer, nullable=False),
    Column("totalisation", Boolean, nullable=False),
    Column("note", Text, nullable=False),
)

# Certificates of Coverage for workers posted abroad: the employer applies and uploads the signed application, the
# International Workers cell issues or rejects it; an issued one can be extended by a new application.
coc_applications = Table(
    "coc_applications", metadata,
    Column("application_id", String(40), primary_key=True),
    Column("kind", String(20), nullable=False),                  # NEW | EXTENSION
    Column("parent_id", String(40)),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("office_id", String(40), nullable=False),
    Column("uan", String(12), nullable=False),
    Column("account_link_id", String(40), nullable=False),
    Column("country", String(60), nullable=False),
    Column("host_employer", String(200), nullable=False),
    Column("posting_from", Date, nullable=False),
    Column("posting_to", Date, nullable=False),
    Column("state", String(30), nullable=False),                 # AWAITING_SIGNED_UPLOAD | SUBMITTED | ISSUED | REJECTED
    Column("signed_upload", JSON),                               # {filename, size_bytes, sha256}
    Column("certificate_no", String(40)),
    Column("decision_reason", Text),
    Column("decided_by", String(80)),
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("decided_at", DateTime(timezone=True)),
)


totalisation_claims = Table(
    "totalisation_claims", metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("reference", String(40), unique=True),
    Column("direction", String(10), nullable=False),
    Column("country", String(60), nullable=False),
    Column("uan", String(12), nullable=False),
    Column("foreign_insurance_no", String(80), nullable=False),
    Column("benefit", String(20), nullable=False),
    Column("periods", JSON, nullable=False),
    Column("months_by_country", JSON, nullable=False),
    Column("liaison_office", String(120), nullable=False),
    Column("notes", Text),
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)
