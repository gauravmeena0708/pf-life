"""Tables owned by member-service (created by migration 0002)."""
from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, MetaData, String, Table, func

metadata = MetaData()
IdType = BigInteger().with_variant(Integer, "sqlite")

members = Table(
    "members", metadata,
    Column("member_id", String(40), primary_key=True),
    Column("uan", String(12), nullable=False, unique=True),
    Column("subject", String(80), unique=True),
    Column("name", String(200), nullable=False),
    Column("date_of_birth", Date, nullable=False),
    Column("gender", String(20), nullable=False),
    Column("mobile_masked", String(40), nullable=False),
    Column("email_masked", String(200), nullable=False),
    Column("bank_ifsc", String(20), nullable=False),
    Column("bank_account_last4", String(4), nullable=False),
    Column("kyc", JSON, nullable=False),
    Column("account_state", String(20), nullable=False, server_default="ACTIVE"),   # ACTIVE | FROZEN (member_freeze process)
    Column("profile_extra", JSON),                           # corrected via Joint Declaration: father's name, etc.
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

employments = Table(
    "employments", metadata,
    Column("account_link_id", String(40), primary_key=True),
    Column("member_id", String(40), ForeignKey("members.member_id"), nullable=False),
    Column("establishment_id", String(40), nullable=False),
    Column("establishment_name", String(200), nullable=False),
    Column("date_of_joining", Date, nullable=False),
    Column("date_of_exit", Date),
    Column("exit_reason", String(40)),
    Column("exit_marked_by", String(20)),                   # MEMBER | EMPLOYER | SEED
    Column("last_contribution_month", String(7)),           # from ContributionPosted.v1 (seeded first)
    Column("transferred_to", String(40)),                   # from TransferPosted.v1 (Form 13)
    Column("form11", JSON),                                 # the new joinee's declaration (previous PF / EPS, international worker)
    Column("registered_by", String(80)),                    # the employer user who registered the joinee (none for seeded rows)
    Column("office_id", String(40)),                        # the field office of the establishment (jurisdiction)
)

# Office postings (synthetic seed): an officer sees members of their own office only (member 360 view).
office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

# KYC seeded by the member (or uploaded in bulk by the employer): checked by a mock verifier (UIDAI / NSDL /
# penny-drop, labelled MOCK), then approved by the employer's authorised signatory with DSC / e-sign.
kyc_requests = Table(
    "kyc_requests", metadata,
    Column("request_id", String(40), primary_key=True),
    Column("member_id", String(40), nullable=False, index=True),
    Column("uan", String(12), nullable=False),
    Column("kyc_type", String(20), nullable=False),          # PAN | BANK | AADHAAR
    Column("masked_value", String(40), nullable=False),
    Column("details", JSON, nullable=False),                  # e.g. ifsc, account_last4, name_on_document
    Column("source", String(20), nullable=False),             # MEMBER | EMPLOYER_BULK
    Column("state", String(30), nullable=False),              # PENDING_EMPLOYER | APPROVED | REJECTED | FAILED_VERIFICATION
    Column("verification", JSON, nullable=False),             # the mock verifier's answer
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("submitted_by", String(80), nullable=False),
    Column("decided_by", String(80)),
    Column("decision_note", String(1000)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("decided_at", DateTime(timezone=True)),
)

kyc_uploads = Table(
    "kyc_uploads", metadata,
    Column("upload_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("uploaded_by", String(80), nullable=False),
    Column("rows", Integer, nullable=False),
    Column("accepted", Integer, nullable=False),
    Column("errors", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# The member's applications (profile corrections, exits, transfers) as the member sees them: *Recent Pending
# Applications* and *Recent Processed Applications*. Kept from ProcessTransitioned.v1 and this service's own
# Mark Exit; used also to refuse a new Mark Exit while another process for the member is ongoing.
member_applications = Table(
    "member_applications", metadata,
    Column("application_id", String(40), primary_key=True),
    Column("uan", String(12), nullable=False, index=True),
    Column("process", String(40), nullable=False),
    Column("title", String(120), nullable=False),
    Column("state", String(40), nullable=False),
    Column("terminal", Boolean, nullable=False),
    Column("account_link_id", String(40)),
    Column("submitted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

notifications = Table(
    "notifications", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("recipient_subject", String(80), nullable=False, index=True),
    Column("template", String(80), nullable=False),
    Column("reference_id", String(80), nullable=False),
    Column("title", String(200), nullable=False),
    Column("body", String(1000), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("read_at", DateTime(timezone=True)),
)

# Every change of contact details, newest last. `verified` rows (seed or an approved recovery) are what an
# account recovery restores. Only masked values are kept.
contact_history = Table(
    "contact_history", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("member_id", String(40), ForeignKey("members.member_id"), nullable=False, index=True),
    Column("mobile_masked", String(40), nullable=False),
    Column("email_masked", String(200), nullable=False),
    Column("source", String(20), nullable=False),          # SEED | MEMBER_CHANGE | RECOVERY
    Column("verified", Boolean, nullable=False),
    Column("changed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

security_reports = Table(
    "security_reports", metadata,
    Column("report_id", String(40), primary_key=True),
    Column("subject", String(80), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("description", String(2000), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

recovery_requests = Table(
    "recovery_requests", metadata,
    Column("request_id", String(40), primary_key=True),
    Column("member_id", String(40), ForeignKey("members.member_id"), nullable=False),
    Column("subject", String(80), nullable=False, index=True),
    Column("reason", String(2000), nullable=False),
    Column("state", String(20), nullable=False),           # PENDING_REVIEW | APPROVED | REJECTED
    Column("restore_to", JSON, nullable=False),            # the last verified contact details, masked
    Column("reviewer_subject", String(80)),
    Column("decision_note", String(2000)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("decided_at", DateTime(timezone=True)),
)

# Every applied Joint Declaration correction: what changed, from what, to what, and who approved it.
member_changes = Table(
    "member_changes", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("request_id", String(40), nullable=False, index=True),
    Column("member_id", String(40), ForeignKey("members.member_id"), nullable=False),
    Column("parameter", String(40), nullable=False),
    Column("old_value", String(200)),
    Column("new_value", String(200), nullable=False),
    Column("approved_by", String(80), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
