"""Tables owned by employer-service (created by migration 0002)."""
from sqlalchemy import JSON, Column, Date, DateTime, Integer, MetaData, String, Table, func

metadata = MetaData()

establishments = Table(
    "establishments", metadata,
    Column("establishment_id", String(40), primary_key=True),
    Column("registration_number", String(40), nullable=False),
    Column("legal_name", String(200), nullable=False),
    Column("office_id", String(40), nullable=False),
    Column("pincode", String(6)),
    Column("city", String(80)),
    Column("district", String(80)),
    Column("coverage_date", Date),
    Column("establishment_type", String(80)),
    Column("industry_group", String(120)),
    Column("exemption_status", String(30)),
    Column("pan", String(10), nullable=False),
    Column("gstin", String(15)),
    Column("status", String(30), nullable=False),        # REGISTERED | VERIFIED | REJECTED
    Column("verified_at", DateTime(timezone=True)),
    Column("version", Integer, nullable=False, server_default="1"),
)

registration_requests = Table(
    "registration_requests", metadata,
    Column("request_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False),
    Column("owner_subject", String(80), nullable=False),
    Column("state", String(40), nullable=False),         # SUBMITTED | MOCK_VERIFICATION_PENDING | VERIFIED | REJECTED
    Column("evidence", JSON),
    Column("result_reason", String(300)),
    Column("verification_ref", String(40)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

grants = Table(
    "grants", metadata,
    Column("grant_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False),
    Column("subject", String(80), nullable=False),
    Column("username", String(80), nullable=False),
    Column("kind", String(20), nullable=False),          # OWNER | OPERATOR | SIGNATORY
    Column("grants", JSON, nullable=False),
    Column("status", String(20), nullable=False),        # ACTIVE | REVOKED
    Column("granted_by", String(80), nullable=False),
    Column("revoked_by", String(80)),
    Column("revocation_reason", String(300)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("revoked_at", DateTime(timezone=True)),
)

directory = Table(  # demo user directory (username -> Keycloak subject), seeded; real systems resolve via the IdP
    "user_directory", metadata,
    Column("username", String(80), primary_key=True),
    Column("subject", String(80), nullable=False),
    Column("role", String(60), nullable=False),
)
