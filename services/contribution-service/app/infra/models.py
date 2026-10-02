"""Standard tables present in every service database (docs/architecture.md §2.2)."""
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

IdType = BigInteger().with_variant(Integer, "sqlite")  # SQLite only autoincrements INTEGER keys (unit tests)


class Base(DeclarativeBase):
    pass


class Outbox(Base):
    """Events written in the same transaction as the state change; a relay publishes them."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    event_type: Mapped[str] = mapped_column(String(120))
    aggregate_type: Mapped[str] = mapped_column(String(60))
    aggregate_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Inbox(Base):
    """IDs of consumed events; a duplicate delivery is acknowledged and ignored."""
    __tablename__ = "inbox"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyKey(Base):
    """Stored response of a command, so a retried command returns the original result."""
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("actor_subject", "operation", "key"),)
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    actor_subject: Mapped[str] = mapped_column(String(80))
    operation: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLocal(Base):
    """This service's audit records, shipped to audit-service through the outbox."""
    __tablename__ = "audit_local"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_subject: Mapped[str] = mapped_column(String(80))
    actor_stakeholder: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str] = mapped_column(String(80))
    correlation_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Establishment(Base):
    __tablename__ = "establishments"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    legal_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    verification_ref: Mapped[str | None] = mapped_column(Text)
    exemption_status: Mapped[str | None] = mapped_column(String(30))
    office_id: Mapped[str | None] = mapped_column(String(40))
    closed_on: Mapped[date | None] = mapped_column(Date)
    last_wage_month: Mapped[str | None] = mapped_column(String(7))


class EstablishmentMember(Base):
    """One row per member ID (account link): a UAN has one per establishment it has worked at."""
    __tablename__ = "establishment_members"
    uan: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[date] = mapped_column(Date)
    account_link_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    member_subject: Mapped[str | None] = mapped_column(String(80))
    establishment_id: Mapped[str] = mapped_column(ForeignKey("establishments.id"))
    date_of_joining: Mapped[date | None] = mapped_column(Date)
    date_of_exit: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    international_worker: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())   # P2.9a: full wages, no ceiling


class ExemptedEstablishment(Base):
    __tablename__ = "exempted_establishments"
    establishment_id: Mapped[str] = mapped_column(ForeignKey("establishments.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    pf_exempt: Mapped[bool] = mapped_column(Boolean)
    pension_exempt: Mapped[bool] = mapped_column(Boolean)
    edli_exempt: Mapped[bool] = mapped_column(Boolean)
    notification_no: Mapped[str] = mapped_column(Text)
    notification_date: Mapped[date] = mapped_column(Date)
    effective_from: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30))
    ended_on: Mapped[date | None] = mapped_column(Date)
    past_accumulations_due: Mapped[date | None] = mapped_column(Date)
    trust_id: Mapped[str] = mapped_column(String(80))
    trust_name: Mapped[str] = mapped_column(Text)
    trust_users: Mapped[list] = mapped_column(JSON)


class TrustPassbookCache(Base):
    __tablename__ = "trust_passbook_cache"
    account_link_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TrustReturn(Base):
    __tablename__ = "trust_returns"
    __table_args__ = (UniqueConstraint("establishment_id", "wage_month", "version"),)
    return_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(ForeignKey("exempted_establishments.establishment_id"), index=True)
    wage_month: Mapped[str] = mapped_column(String(7))
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20))
    content: Mapped[dict] = mapped_column(JSON)
    score: Mapped[float] = mapped_column(Float)
    parts: Mapped[dict] = mapped_column(JSON)
    balance_due_paise: Mapped[int] = mapped_column(BigInteger)
    late_transfer_days: Mapped[int] = mapped_column(Integer)
    claims_pending: Mapped[int] = mapped_column(Integer)
    filed_by: Mapped[str] = mapped_column(String(80))
    filed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrustFlag(Base):
    __tablename__ = "trust_flags"
    flag_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(ForeignKey("exempted_establishments.establishment_id"), index=True)
    wage_month: Mapped[str] = mapped_column(String(7))
    category: Mapped[str] = mapped_column(String(1))
    code: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    action: Mapped[str | None] = mapped_column(String(40))
    action_note: Mapped[str | None] = mapped_column(Text)
    actioned_by: Mapped[str | None] = mapped_column(String(80))
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InoperativeVerification(Base):
    __tablename__ = "inoperative_verifications"
    account_link_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    uan: Mapped[str] = mapped_column(String(32))
    co_workers: Mapped[int] = mapped_column(Integer)
    verified_by_office: Mapped[str] = mapped_column(String(80))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountReactivation(Base):
    __tablename__ = "account_reactivations"
    account_link_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    uan: Mapped[str] = mapped_column(String(32))
    balance_paise: Mapped[int] = mapped_column(BigInteger)
    approved_by: Mapped[str] = mapped_column(String(80))
    approved_by_role: Mapped[str] = mapped_column(String(60))
    note: Mapped[str] = mapped_column(Text)
    reactivated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InoperativeSearchRef(Base):
    __tablename__ = "inoperative_search_refs"
    search_ref: Mapped[str] = mapped_column(String(80), primary_key=True)
    account_link_id: Mapped[str] = mapped_column(String(80), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ECRFiling(Base):
    __tablename__ = "ecr_filings"
    __table_args__ = (UniqueConstraint("establishment_id", "wage_month", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(ForeignKey("establishments.id"))
    wage_month: Mapped[str] = mapped_column(String(7))
    filing_type: Mapped[str] = mapped_column(String(20))
    format: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30))
    preparer_subject: Mapped[str] = mapped_column(String(80))
    approver_subject: Mapped[str | None] = mapped_column(String(80))
    rule_version: Mapped[str] = mapped_column(String(80))
    validation_report: Mapped[dict | None] = mapped_column(JSON)
    trrn: Mapped[str | None] = mapped_column(String(17), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PrincipalEmployerTag(Base):
    __tablename__ = "principal_employer_tags"
    filing_id: Mapped[str] = mapped_column(ForeignKey("ecr_filings.id"), primary_key=True)
    uan: Mapped[str] = mapped_column(String(32), primary_key=True)
    principal_establishment_id: Mapped[str] = mapped_column(String(80))
    work_order_ref: Mapped[str] = mapped_column(String(120))
    epf_wages_paise: Mapped[int] = mapped_column(BigInteger)
    contribution_paise: Mapped[int] = mapped_column(BigInteger)


class Challan(Base):
    __tablename__ = "challans"
    trrn: Mapped[str] = mapped_column(String(17), primary_key=True)
    filing_id: Mapped[str | None] = mapped_column(ForeignKey("ecr_filings.id"), unique=True, nullable=True)   # none for a direct challan
    establishment_id: Mapped[str] = mapped_column(ForeignKey("establishments.id"))
    status: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(20), server_default="ECR")      # ECR | DIRECT_ADMIN | DIRECT_MISC
    applied_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")   # a misc challan knocked off against demands
    total_paise: Mapped[int] = mapped_column(BigInteger)
    breakdown: Mapped[dict] = mapped_column(JSON)
    payment_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemoCalculation(Base):
    __tablename__ = "demo_calculations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    epf_wages_paise: Mapped[int] = mapped_column(BigInteger)
    eps_wages_paise: Mapped[int] = mapped_column(BigInteger)
    age_years: Mapped[int] = mapped_column(Integer)
    rule_version: Mapped[str] = mapped_column(String(80))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Journal(Base):
    __tablename__ = "journals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    business_key: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reverses_journal_id: Mapped[str | None] = mapped_column(ForeignKey("journals.id"))
    filing_id: Mapped[str | None] = mapped_column(ForeignKey("ecr_filings.id"))
    claim_id: Mapped[str | None] = mapped_column(String(40))


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    account_code: Mapped[str] = mapped_column(String(40))
    side: Mapped[str] = mapped_column(String(6))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    account_link_id: Mapped[str | None] = mapped_column(String(80))
    share: Mapped[str | None] = mapped_column(String(20))


class InterestPosting(Base):
    """One interest journal per account, financial year and rule version (the rate declared in that version).
    A revised rate posts only the difference as a further journal; nothing is edited (ADR-0003)."""
    __tablename__ = "interest_postings"
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"), primary_key=True)
    financial_year: Mapped[str] = mapped_column(String(7), index=True)
    account_link_id: Mapped[str] = mapped_column(String(80), index=True)
    rule_version: Mapped[str] = mapped_column(String(60))
    rate_bp: Mapped[int] = mapped_column(Integer)
    employee_paise: Mapped[int] = mapped_column(BigInteger)
    employer_paise: Mapped[int] = mapped_column(BigInteger)
    revision: Mapped[int] = mapped_column(Integer)          # 0 = first credit for the year, 1.. = rate revisions
    posted_by: Mapped[str] = mapped_column(String(80))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransferPosting(Base):
    """A Form 13 transfer posted to the ledger: the source of the member's Annexure K."""
    __tablename__ = "transfer_postings"
    transfer_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    uan: Mapped[str] = mapped_column(String(32), index=True)
    member_subject: Mapped[str | None] = mapped_column(String(80), index=True)
    from_account_link_id: Mapped[str] = mapped_column(String(80))
    to_account_link_id: Mapped[str] = mapped_column(String(80))
    employee_paise: Mapped[int] = mapped_column(BigInteger)
    employer_paise: Mapped[int] = mapped_column(BigInteger)
    journal_id: Mapped[str | None] = mapped_column(ForeignKey("journals.id"))
    approved_by: Mapped[str] = mapped_column(String(80))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    recredit_journal_id: Mapped[str | None] = mapped_column(String(36))    # the transfer was recredited (reversed)


class TransferLeg(Base):
    __tablename__ = "transfer_legs"
    transfer_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    uan: Mapped[str] = mapped_column(String(32), index=True)
    from_account_link_id: Mapped[str] = mapped_column(String(80))
    to_account_link_id: Mapped[str] = mapped_column(String(80))
    pf_leg: Mapped[str] = mapped_column(String(30))
    eps_leg: Mapped[str] = mapped_column(String(30))
    direction: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EstablishmentFreeze(Base):
    """An establishment under a freeze order (establishment_freeze process): no ECR is approved or submitted."""
    __tablename__ = "establishment_freezes"
    establishment_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(40))
    order_ref: Mapped[str | None] = mapped_column(String(80))
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnnexureKVdrReco(Base):
    """ANNEXURE K VDR RECO: an inter-office Annexure K amount matched with the VDR receipt of the transfer."""
    __tablename__ = "annexure_k_vdr_recos"
    annexure_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    receipt_ref: Mapped[str] = mapped_column(String(60))
    vdr_receipt_paise: Mapped[int] = mapped_column(BigInteger)
    annexure_amount_paise: Mapped[int] = mapped_column(BigInteger)
    result: Mapped[str] = mapped_column(String(20))
    reconciled_by: Mapped[str] = mapped_column(String(80))
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Demand(Base):
    """A payable demand raised when contributions are paid after the due date: 14B damages or 7Q interest."""
    __tablename__ = "demands"
    demand_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(20))                   # DAMAGES_14B | INTEREST_7Q
    trrn: Mapped[str] = mapped_column(String(17))                   # the challan paid late
    wage_month: Mapped[str] = mapped_column(String(7))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    days_late: Mapped[int] = mapped_column(Integer)
    working: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(20))                  # OPEN | KNOCKED_OFF
    settled_by: Mapped[str | None] = mapped_column(String(40))      # the knock-off
    realised_paise: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnockOff(Base):
    """14B / 7Q knock-off: the DA (Compliance) matches demands with a paid miscellaneous challan; the SS approves."""
    __tablename__ = "damages_knock_offs"
    knock_off_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(String(80), index=True)
    trrn: Mapped[str] = mapped_column(String(17))
    demand_ids: Mapped[list] = mapped_column(JSON)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(20))                  # PROPOSED | APPROVED | REJECTED
    proposed_by: Mapped[str] = mapped_column(String(80))
    decided_by: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VdrEntry(Base):
    """A receipt that arrived outside the online challan flow (cheque, DD, an unmatched credit), recorded by Cash;
    the DA (Accounts) allocates it to TRRNs (TRRN adjustment) or rejects it (e.g. a dishonoured cheque)."""
    __tablename__ = "vdr_entries"
    vdr_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(String(80), index=True)
    instrument: Mapped[str] = mapped_column(String(20))              # CHEQUE | DD | NEFT_UNMATCHED
    instrument_ref: Mapped[str] = mapped_column(String(60))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    allocated_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")
    received_on: Mapped[date] = mapped_column(Date)
    state: Mapped[str] = mapped_column(String(20))                   # UNRECONCILED | PARTIAL | RECONCILED | REJECTED
    allocations: Mapped[list] = mapped_column(JSON)
    remarks: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerAdjustment(Base):
    """Appendix E (CITES manual): a field-office adjustment of a member ID's balances, with the notesheet; the DA
    proposes, the APFC approves and only then is it posted."""
    __tablename__ = "ledger_adjustments"
    adjustment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    account_link_id: Mapped[str] = mapped_column(String(80), index=True)
    uan: Mapped[str] = mapped_column(String(32))
    appendix_type: Mapped[str] = mapped_column(String(30))           # OTHER | INTEREST_ON_RETURNS | EPS_DIVERSION | EXCESS_INTEREST_DEBIT
    lines: Mapped[list] = mapped_column(JSON)
    notesheet_no: Mapped[str] = mapped_column(String(60))
    notesheet_date: Mapped[date] = mapped_column(Date)
    remarks: Mapped[str] = mapped_column(Text)
    attachment: Mapped[dict | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20))                   # PROPOSED | APPROVED | REJECTED
    proposed_by: Mapped[str] = mapped_column(String(80))
    decided_by: Mapped[str | None] = mapped_column(String(80))
    decision_note: Mapped[str | None] = mapped_column(Text)
    journal_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InterestRateDeclaration(Base):
    """The approved annual interest rate as recorded by HO F&A (CBT recommendation, Ministry concurrence), P2.8d. It
    reaches the rule set as a draft that HO's maker-checker publishes; crediting uses only the published rate."""
    __tablename__ = "interest_rate_declarations"
    declaration_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    financial_year: Mapped[str] = mapped_column(String(7), index=True)
    rate_bp: Mapped[int] = mapped_column(Integer)
    cbt_recommended_on: Mapped[date] = mapped_column(Date)
    ministry_concurrence_ref: Mapped[str] = mapped_column(String(80))
    ministry_concurrence_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PastAccumulationIngestion(Base):
    """A surrendered PF trust's member ledgers taken over by EPFO (P2.8d): one batch per transfer reference."""
    __tablename__ = "past_accumulation_ingestions"
    batch_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(String(80), index=True)
    transfer_reference: Mapped[str] = mapped_column(String(80), unique=True)
    lines: Mapped[list] = mapped_column(JSON)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    ingested_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OfficeStaff(Base):
    """Who is posted where (P2.9d): the exemption cell's office scopes the trusts it supervises. From the seed, then
    StaffPostingChanged.v1 (epfo_persistence.postings)."""
    __tablename__ = "office_staff"
    subject: Mapped[str] = mapped_column(String(80), primary_key=True)
    stakeholder: Mapped[str] = mapped_column(String(60))
    office_id: Mapped[str] = mapped_column(String(40))

class PmvbryEstablishment(Base):
    __tablename__ = 'pmvbry_establishments'
    establishment_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    manufacturing: Mapped[bool] = mapped_column(Boolean, default=False)
    gstin: Mapped[str | None] = mapped_column(String(32))
    bank_account_ref: Mapped[str | None] = mapped_column(String(120))
    option_exercised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    excluded_reason: Mapped[str | None] = mapped_column(Text)


class PmvbryEcrRow(Base):
    __tablename__ = 'pmvbry_ecr_rows'
    establishment_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    wage_month: Mapped[str] = mapped_column(String(7), primary_key=True)
    uan: Mapped[str] = mapped_column(String(32), primary_key=True)
    epf_wage_paise: Mapped[int] = mapped_column(BigInteger)
    gross_wage_paise: Mapped[int] = mapped_column(BigInteger)
    date_of_joining: Mapped[date] = mapped_column(Date)
    contribution_received: Mapped[bool] = mapped_column(Boolean)
    kind: Mapped[str] = mapped_column(String(20))
    face_authenticated: Mapped[bool] = mapped_column(Boolean)
    aadhaar_authenticated: Mapped[bool] = mapped_column(Boolean)
    aadhaar_seeded_bank: Mapped[bool] = mapped_column(Boolean)


class PmvbryLiteracy(Base):
    __tablename__ = 'pmvbry_literacy'
    uan: Mapped[str] = mapped_column(String(32), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    member_subject: Mapped[str] = mapped_column(String(80))


class PmvbryPayment(Base):
    __tablename__ = 'pmvbry_payments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payment_key: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    beneficiary: Mapped[str] = mapped_column(String(80))
    establishment_id: Mapped[str] = mapped_column(String(80))
    uan: Mapped[str | None] = mapped_column(String(32))
    instalment: Mapped[int | None] = mapped_column(Integer)
    cycle_month: Mapped[str | None] = mapped_column(String(7))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(10))
    run_id: Mapped[str] = mapped_column(String(36))
    mock_reference: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PmvbryInquiry(Base):
    """P2.11d: the compliance inquiries that withhold PMVBRY Part B (scheme guidelines 6.2.3): pending, or ordered and not complied with."""
    __tablename__ = "pmvbry_inquiries"
    case_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(String(40), index=True)
    section: Mapped[str] = mapped_column(String(4))
    diary_no: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(10))           # PENDING | ORDERED
    demand_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class EecDeclaration(Base):
    """P2.26b: an employee enrolled under the Employees' Enrolment Campaign, 2026 (PIB 2300475): left out between 1 Apr 2009
    and 31 Mar 2026, declared by the employer, the past dues paid on one challan (kind EEC)."""
    __tablename__ = "eec_declarations"
    declaration_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(String(40), index=True)
    uan: Mapped[str] = mapped_column(String(32))
    account_link_id: Mapped[str] = mapped_column(String(80), unique=True)          # one declaration per member ID
    monthly_wages_paise: Mapped[int] = mapped_column(BigInteger)
    employee_share_deducted: Mapped[bool] = mapped_column(Boolean)
    from_month: Mapped[str] = mapped_column(String(7))
    to_month: Mapped[str] = mapped_column(String(7))
    months: Mapped[list] = mapped_column(JSON)                                      # the month-by-month working
    totals: Mapped[dict] = mapped_column(JSON)
    trrn: Mapped[str] = mapped_column(String(17))
    state: Mapped[str] = mapped_column(String(10))                                  # DUE | PAID
    declared_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PastAccumulationReconciliation(Base):
    """PAST ACCUM VDR RECO (SOP on surrender, Dec 2023, (xi)-(xxiv)): the receipts of a trust's past accumulations — the cash
    component by demand draft (a VDR entry), the SDS balance and the securities (HO Investment Division's reference) —
    matched with the members credited and the Form SE-6 statement. DA (Accounts) proposes, the APFC approves."""
    __tablename__ = "past_accumulation_reconciliations"
    reco_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    establishment_id: Mapped[str] = mapped_column(String(80), index=True)
    statement_total_paise: Mapped[int] = mapped_column(BigInteger)          # Form SE-6
    receipts: Mapped[list] = mapped_column(JSON)
    receipts_paise: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(12))                            # PROPOSED | RECONCILED | SHORT | REJECTED
    summary: Mapped[dict] = mapped_column(JSON)
    proposed_by: Mapped[str] = mapped_column(String(80))
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

