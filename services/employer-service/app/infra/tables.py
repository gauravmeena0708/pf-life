"""Tables owned by employer-service (created by migration 0002)."""
from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, DateTime, Index, Integer, MetaData, String, Table, Text, func

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
    Column("frozen_at", DateTime(timezone=True)),              # set while a freeze order stands (establishment_freeze)
    Column("freeze", JSON),                                     # category, order reference, reason, case
    Column("address", JSON),                                    # line, city, district, pincode; email, phone (P2.6)
    Column("kyc", JSON),                                        # PAN / TAN / GSTIN / CIN / LIN: masked value, status, ref
    Column("bank_accounts", JSON),                              # remittance accounts (seeded, masked)
    Column("coverage", JSON),                                   # the circle officer's coverage decision (OLRE)
    Column("closed_on", Date),
)

establishment_exemptions = Table(
    "establishment_exemptions", metadata,
    Column("establishment_id", String(40), primary_key=True),
    Column("kind", String(30), nullable=False),
    Column("pf_exempt", Boolean, nullable=False),
    Column("pension_exempt", Boolean, nullable=False),
    Column("edli_exempt", Boolean, nullable=False),
    Column("notification_no", String(120), nullable=False),
    Column("notification_date", Date, nullable=False),
    Column("effective_from", Date, nullable=False),
    Column("status", String(30), nullable=False),
    Column("trust_id", String(40), nullable=False),
    Column("trust_name", String(200), nullable=False),
    Column("trust_users", JSON, nullable=False),
    Column("ended_on", Date),
)

trust_audits = Table(
    "trust_audits", metadata,
    Column("audit_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("financial_year", String(7), nullable=False),
    Column("auditor_name", String(200), nullable=False),
    Column("auditor_registration", String(100), nullable=False),
    Column("opening_corpus_paise", BigInteger, nullable=False),
    Column("contributions_paise", BigInteger, nullable=False),
    Column("interest_credited_paise", BigInteger, nullable=False),
    Column("claims_paid_paise", BigInteger, nullable=False),
    Column("other_paise", BigInteger, nullable=False),
    Column("closing_corpus_paise", BigInteger, nullable=False),
    Column("opinion", String(20), nullable=False),
    Column("observations", Text),
    Column("status", String(20), nullable=False),
    Column("due_on", Date, nullable=False),
    Column("late_days", Integer, nullable=False),
    Column("filed_at", DateTime(timezone=True), nullable=False),
    Column("filed_by", String(80), nullable=False),
)

exemption_proceedings = Table(
    "exemption_proceedings", metadata,
    Column("proceeding_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("kind", String(20), nullable=False),
    Column("stage", String(40), nullable=False),
    Column("open", Boolean, nullable=False),
    Column("details", JSON, nullable=False),
    Column("surrender_date", Date),
    Column("reply_due", Date),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

exemption_proceeding_steps = Table(
    "exemption_proceeding_steps", metadata,
    Column("step_id", String(40), primary_key=True),
    Column("proceeding_id", String(40), nullable=False, index=True),
    Column("step", String(40), nullable=False),
    Column("stage_after", String(40), nullable=False),
    Column("actor_subject", String(80), nullable=False),
    Column("actor_stakeholder", String(60), nullable=False),
    Column("note", Text, nullable=False),
    Column("reference", String(200)),
    Column("at", DateTime(timezone=True), nullable=False),
)

Index("uq_trust_audit_current_year", trust_audits.c.establishment_id, trust_audits.c.financial_year,
      unique=True, sqlite_where=trust_audits.c.status == "CURRENT",
      postgresql_where=trust_audits.c.status == "CURRENT")
Index("uq_exemption_proceeding_open", exemption_proceedings.c.establishment_id, unique=True,
      sqlite_where=exemption_proceedings.c.open.is_(True),
      postgresql_where=exemption_proceedings.c.open.is_(True))

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
    Column("source", String(30)),
    Column("source_ref", String(80)),
)

offices = Table(
    "offices", metadata,
    Column("office_id", String(40), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("zone_id", String(40)),
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


# Office postings (synthetic seed): an officer acts on establishments of their own office only.
office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

# OLRE: the office's scrutiny of a new registration — documents seen, notes, the compliance e-file.
registration_scrutiny = Table(
    "registration_scrutiny", metadata,
    Column("request_id", String(40), primary_key=True),
    Column("efile_no", String(60), nullable=False),
    Column("notes", JSON, nullable=False),
    Column("scrutinised_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# A change the establishment asks for (profile: address / contact; configuration: type, industry, schemes); the
# office decides it, and only then does the establishment record change.
change_requests = Table(
    "establishment_change_requests", metadata,
    Column("request_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("kind", String(20), nullable=False),                 # PROFILE | CONFIGURATION
    Column("changes", JSON, nullable=False),                    # field -> {from, to}
    Column("reason", Text, nullable=False),
    Column("state", String(20), nullable=False),                # PENDING | APPROVED | REJECTED
    Column("requested_by", String(80), nullable=False),
    Column("decided_by", String(80)),
    Column("decision_note", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("decided_at", DateTime(timezone=True)),
)

# Form 5A: the ownership / management return, every version kept (signed with DSC / e-sign, mock).
ownership_declarations = Table(
    "ownership_declarations", metadata,
    Column("declaration_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("nature_of_business", String(200), nullable=False),
    Column("persons", JSON, nullable=False),                    # name, designation, role, PAN (masked), share %
    Column("signed_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# Branches / departments (sub-codes; Form 2A).
branches = Table(
    "branches", metadata,
    Column("branch_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("sub_code", String(60), nullable=False, unique=True),
    Column("name", String(200), nullable=False),
    Column("kind", String(20), nullable=False),                 # BRANCH | DEPARTMENT
    Column("address", JSON, nullable=False),
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# A principal employer's contractors (their own establishments), with the work order.
contractors = Table(
    "contractors", metadata,
    Column("contractor_id", String(40), primary_key=True),
    Column("principal_establishment_id", String(40), nullable=False, index=True),
    Column("contractor_registration_number", String(40), nullable=False),
    Column("contractor_name", String(200), nullable=False),
    Column("contractor_establishment_id", String(40)),          # when the contractor is registered with EPFO
    Column("work_order_ref", String(80), nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
    Column("linked_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# DSC / Aadhaar e-sign registration of an authorised signatory (Establishment > e-sign Registration), backed by the
# scanned request letter, approved by the PF office; a revocation is backed by a revoke letter the office accepts.
signature_registrations = Table(
    "signature_registrations", metadata,
    Column("reg_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("grant_id", String(40), nullable=False, index=True),          # the signatory
    Column("purpose", String(10), nullable=False),                       # REGISTER | REVOKE
    Column("method", String(10)),                                        # DSC | ESIGN (registration)
    Column("details", JSON, nullable=False),                             # certificate / e-sign particulars (mock, masked)
    Column("letter", JSON),                                              # file name, size, SHA-256 of the signed letter
    Column("state", String(20), nullable=False),                         # LETTER_PENDING | PENDING_OFFICE | APPROVED | REJECTED | REVOKED
    Column("decided_by", String(80)),
    Column("decision_note", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("decided_at", DateTime(timezone=True)),
)
