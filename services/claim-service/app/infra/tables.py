"""Tables owned by claim-service (created by migration 0002)."""
from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, DateTime, Integer, LargeBinary, MetaData, String, Table, Text, UniqueConstraint, false as sa_false, true as sa_true, func

from app.infra.models import IdType

metadata = MetaData()

# Projection of member accounts: seeded opening balances, then kept current from ContributionPosted.v1
# and ClaimDebitPosted.v1. Claim eligibility is evaluated against this, never against another service's DB.
accounts = Table(
    "accounts", metadata,
    Column("account_link_id", String(40), primary_key=True),
    Column("member_subject", String(80), index=True),
    Column("member_name", String(120)),
    Column("establishment_id", String(40), nullable=False),
    Column("office_id", String(40), nullable=False),
    Column("date_of_joining", Date, nullable=False),
    Column("date_of_exit", Date),
    Column("employee_paise", BigInteger, nullable=False, server_default="0"),
    Column("employer_paise", BigInteger, nullable=False, server_default="0"),
    Column("uan", String(12), index=True),
    Column("frozen", Boolean, nullable=False, server_default=sa_false()),   # from AccountFrozen.v1 / AccountDefrozen.v1
    Column("pan_verified", Boolean, nullable=False, server_default=sa_false()),   # decides the TDS rate
    Column("interest_paise", BigInteger, nullable=False, server_default="0"),     # interest credited (InterestCredited.v1), for the CAD
    Column("deceased_on", Date),                                                  # a death in service (exit reason) or seeded
    Column("is_primary", Boolean, nullable=False, server_default=sa_false()),     # the member's primary member ID (P2.7d)
    Column("set_key", String(200)),                                               # the UANs of the member's Aadhaar-verified set
    Column("aadhaar_verified", Boolean, nullable=False, server_default=sa_true()),  # not verified: claims wait for the employer's attestation (P2.8b)
    Column("international_worker", Boolean, nullable=False, server_default=sa_false()),   # P2.9a: the international-worker rules apply
    Column("nationality", String(60)),
    Column("date_of_birth", Date),                                                          # for age conditions (retirement)
)

# Office staff directory (synthetic seed): which office an officer acts for.
office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

# Synthetic exemption directory, including the subjects allowed to act for the trust.
exempted_establishments = Table(
    "exempted_establishments", metadata,
    Column("establishment_id", String(40), primary_key=True),
    Column("kind", String(30), nullable=False),
    Column("pf_exempt", Boolean, nullable=False),
    Column("pension_exempt", Boolean, nullable=False),
    Column("edli_exempt", Boolean, nullable=False),
    Column("notification_no", String(100), nullable=False),
    Column("notification_date", Date, nullable=False),
    Column("effective_from", Date, nullable=False),
    Column("status", String(20), nullable=False),
    Column("trust_id", String(40), nullable=False),
    Column("trust_name", String(160), nullable=False),
    Column("trust_users", JSON, nullable=False),
)

annexure_k_requests = Table(
    "annexure_k_requests", metadata,
    Column("annexure_id", String(40), primary_key=True),
    Column("transfer_id", String(80), nullable=False, unique=True),
    Column("uan", String(12), nullable=False),
    Column("from_account_link_id", String(40), nullable=False),
    Column("to_account_link_id", String(40), nullable=False),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("trust_id", String(40), nullable=False),
    Column("state", String(20), nullable=False),
    Column("employee_paise", BigInteger),
    Column("employer_paise", BigInteger),
    Column("service_from", Date),
    Column("service_to", Date),
    Column("breaks_months", Integer),
    Column("interest_note", Text),
    Column("receipt_ref", String(100)),
    Column("received_paise", BigInteger),
    Column("difference_paise", BigInteger),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

claims = Table(
    "claims", metadata,
    Column("claim_id", String(40), primary_key=True),
    Column("member_subject", String(80), nullable=False, index=True),
    Column("account_link_id", String(40), nullable=False),
    Column("claim_type", String(40), nullable=False),
    Column("form_type", String(10), nullable=False),
    Column("amount_paise", BigInteger, nullable=False),
    Column("state", String(40), nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("rule_version", String(40), nullable=False),
    Column("office_id", String(40), nullable=False),
    Column("evaluation", JSON, nullable=False),      # input snapshot, limits and trace, for deterministic replay
    Column("summary", Text, nullable=False),
    Column("decision_reason", Text),
    Column("debit_journal_id", String(40)),
    Column("payment_id", String(60)),
    Column("payment_attempt", Integer, nullable=False, server_default="0"),
    Column("prior_state", String(40)),                 # the state a frozen claim was held in
    Column("recommended", Boolean, nullable=False, server_default=sa_false()),   # a recommendation was recorded
    Column("payee_ifsc", String(11)),                  # corrected bank details for a re-disbursement
    Column("payee_account_last4", String(4)),
    Column("tax", JSON),                               # TDS worked out at the first payment instruction, then fixed
    Column("death_of_uan", String(12)),                # a death claim (Form 20 / 5IF): the deceased member's UAN; member_subject is the claimant
    Column("composite_ref", String(40), index=True),    # shared by Form 20 and Form 5IF filed together
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

# What the member sees as the claim timeline. Officers appear by role, never by name.
claim_timeline = Table(
    "claim_timeline", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("claim_id", String(40), nullable=False, index=True),
    Column("at", DateTime(timezone=True), server_default=func.now()),
    Column("state", String(40), nullable=False),
    Column("actor_role", String(60), nullable=False),
    Column("note", Text, nullable=False),
)

# Open advisory risk signals per member (from RiskSignalRaised.v1 / RiskSignalReviewed.v1). A flag never
# blocks or rejects a claim; it only sends the claim to an officer instead of automatic approval.
risk_flags = Table(
    "risk_flags", metadata,
    Column("signal_id", String(40), primary_key=True),
    Column("subject", String(80), nullable=False, index=True),
    Column("status", String(30), nullable=False),        # OPEN | NEEDS_MORE_EVIDENCE | CONFIRMED | BENIGN
)

# Form 15G / 15H self-declarations: one per member and financial year; waives TDS when the policy allows it.
tax_declarations = Table(
    "tax_declarations", metadata,
    Column("member_subject", String(80), primary_key=True),
    Column("financial_year", String(7), primary_key=True),
    Column("form", String(3), nullable=False),
    Column("submitted_at", DateTime(timezone=True), server_default=func.now()),
)

# Documents a member uploads with a claim. POC stand-in for the object store: kept here, capped at 1 MB,
# with the SHA-256 recorded so a later copy can be checked.
claim_documents = Table(
    "claim_documents", metadata,
    Column("doc_id", String(40), primary_key=True),
    Column("claim_id", String(40), nullable=False, index=True),
    Column("filename", String(200), nullable=False),
    Column("content_type", String(60), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("content", LargeBinary, nullable=False),
    Column("uploaded_at", DateTime(timezone=True), server_default=func.now()),
)

# Claim Approval Docket (CITES): generated by the initiator and again by each verifier and the approver before they
# act — gross, the interest included in the balance, TDS and net payable — with the rule set and static-data
# versions it used. Payment follows the last one.
cads = Table(
    "cads", metadata,
    Column("cad_id", String(40), primary_key=True),
    Column("claim_id", String(40), nullable=False, index=True),   # one per level: each officer regenerates it (CITES manuals)
    Column("officer_role", String(60)),
    Column("gross_paise", BigInteger, nullable=False),
    Column("interest_paise", BigInteger, nullable=False),
    Column("tds_paise", BigInteger, nullable=False),
    Column("net_paise", BigInteger, nullable=False),
    Column("tax", JSON, nullable=False),
    Column("rule_version", String(60), nullable=False),
    Column("static_data_version", String(40), nullable=False),
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# Nominations on record for a member (synthetic seed; e-nomination is planned): who may claim on the member's death.
nominations = Table(
    "nominations", metadata,
    Column("nomination_id", String(40), primary_key=True),
    Column("uan", String(12), nullable=False, index=True),
    Column("name", String(120), nullable=False),
    Column("relation", String(30), nullable=False),
    Column("share_bp", Integer, nullable=False),
    Column("subject", String(80), index=True),                  # the nominee's login, when there is one
    Column("bank_ifsc", String(11)),
    Column("bank_account_last4", String(4)),
)

# The beneficiaries of a death claim and their shares: from the latest nomination, a list of surviving family
# members, or added. The APFC amends a share (with a reason); a share already settled in the legacy system is kept.
claim_beneficiaries = Table(
    "claim_beneficiaries", metadata,
    Column("beneficiary_id", String(40), primary_key=True),
    Column("claim_id", String(40), nullable=False, index=True),
    Column("name", String(120), nullable=False),
    Column("relation", String(30), nullable=False),
    Column("share_bp", Integer, nullable=False),
    Column("source", String(30), nullable=False),               # E_NOMINATION | LSM | ADDED_BY_CLAIMANT
    Column("bank_account_last4", String(4)),
    Column("legacy_settled_paise", BigInteger, nullable=False, server_default="0"),
    Column("disbursed_paise", BigInteger, nullable=False, server_default="0"),
    Column("amendments", JSON, nullable=False),
)

# Paper claims and updations inwarded at the PRO counter.
physical_intakes = Table(
    "physical_intakes", metadata,
    Column("intake_id", String(40), primary_key=True),
    Column("form_type", String(40), nullable=False),
    Column("uan", String(12), nullable=False),
    Column("ppo_id", String(40)),
    Column("filed_by", String(20), nullable=False),
    Column("claim_mode", String(20), nullable=False),
    Column("details", JSON, nullable=False),
    Column("office_id", String(40), nullable=False),
    Column("inwarded_by", String(80), nullable=False),
    Column("state", String(20), nullable=False),                # INWARDED | ROUTED
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# A payment scroll: approved claims of an office sent to the bank together; returns are reconciled against it.
payment_scrolls = Table(
    "payment_scrolls", metadata,
    Column("scroll_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False),
    Column("claim_ids", JSON, nullable=False),
    Column("total_paise", BigInteger, nullable=False),
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("reconciliation", JSON),
)

# ANNEXURE K FILE: the inter-office transfer statement of each posted Form 13, outward from the office of the
# previous member ID and inward to the office of the new one, reconciled with the transfer and member records.
annexure_k_files = Table(
    "annexure_k_files", metadata,
    Column("annexure_id", String(40), primary_key=True),          # the transfer's ID
    Column("uan", String(12), nullable=False),
    Column("from_account_link_id", String(40), nullable=False),
    Column("to_account_link_id", String(40), nullable=False),
    Column("from_office_id", String(40), nullable=False, index=True),
    Column("to_office_id", String(40), nullable=False, index=True),
    Column("employee_paise", BigInteger, nullable=False),
    Column("employer_paise", BigInteger, nullable=False),
    Column("reco_status", String(20), nullable=False),            # PENDING | MATCHED | MISMATCH
    Column("reco", JSON),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# The member's KYC-verified bank accounts (seeded, then MemberKycUpdated.v1): a claim not yet in payment can be
# switched to any of them (P2.8b).
member_bank_accounts = Table(
    "member_bank_accounts", metadata,
    Column("uan", String(12), primary_key=True),
    Column("bank_ifsc", String(20), primary_key=True),
    Column("bank_account_last4", String(4), primary_key=True),
    Column("verified_at", DateTime(timezone=True), server_default=func.now()),
)

# Auto-transfers on a change of job (P2.8b): an exited member ID of the member's Aadhaar-verified set with a balance
# is offered for transfer into the primary member ID; the member confirms, contribution-service posts it.
auto_transfers = Table(
    "auto_transfers", metadata,
    Column("transfer_id", String(80), primary_key=True),
    Column("member_subject", String(80), nullable=False, index=True),
    Column("uan", String(12), nullable=False),
    Column("from_account_link_id", String(40), nullable=False),
    Column("to_account_link_id", String(40), nullable=False),
    Column("amount_paise", BigInteger, nullable=False),
    Column("state", String(20), nullable=False),            # CONFIRMED | POSTED
    Column("confirmed_at", DateTime(timezone=True), server_default=func.now()),
    Column("posted_at", DateTime(timezone=True)),
)

# A filed illustrative Form 26Q is an immutable snapshot for one office and quarter.
tds_filings = Table(
    "tds_filings", metadata,
    Column("filing_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False),
    Column("financial_year", String(7), nullable=False),
    Column("quarter", String(2), nullable=False),
    Column("deductees", JSON, nullable=False),
    Column("amount_paid_paise", BigInteger, nullable=False),
    Column("tds_paise", BigInteger, nullable=False),
    Column("acknowledgement", String(80), nullable=False),
    Column("filed_by", String(80), nullable=False),
    Column("filed_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("office_id", "financial_year", "quarter"),
)
