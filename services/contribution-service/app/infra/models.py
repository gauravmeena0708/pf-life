"""Standard tables present in every service database (docs/architecture.md §2.2)."""
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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


class EstablishmentMember(Base):
    __tablename__ = "establishment_members"
    uan: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[date] = mapped_column(Date)
    account_link_id: Mapped[str] = mapped_column(String(80), unique=True)
    member_subject: Mapped[str | None] = mapped_column(String(80))
    establishment_id: Mapped[str] = mapped_column(ForeignKey("establishments.id"))
    date_of_joining: Mapped[date | None] = mapped_column(Date)
    date_of_exit: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


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


class Challan(Base):
    __tablename__ = "challans"
    trrn: Mapped[str] = mapped_column(String(17), primary_key=True)
    filing_id: Mapped[str] = mapped_column(ForeignKey("ecr_filings.id"), unique=True)
    establishment_id: Mapped[str] = mapped_column(ForeignKey("establishments.id"))
    status: Mapped[str] = mapped_column(String(30))
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
