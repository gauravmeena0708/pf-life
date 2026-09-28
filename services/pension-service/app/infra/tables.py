"""Tables owned by pension-service (created by migration 0002). Synthetic pensioners only."""
from sqlalchemy import JSON, BigInteger, Column, Date, DateTime, Integer, MetaData, String, Table, Text, UniqueConstraint, func

from app.infra.models import IdType

metadata = MetaData()

# One row per pension in payment (PPO). The monthly amount in force for a month comes from the original
# amount and the approved revisions (domain/pension.py amount_for), never from an edited figure.
pensioners = Table(
    "pensioners", metadata,
    Column("ppo_id", String(40), primary_key=True),
    Column("subject", String(80), index=True),                  # the pensioner's login, when there is one
    Column("name", String(120), nullable=False),
    Column("uan", String(12), nullable=False),
    Column("date_of_birth", Date, nullable=False),
    Column("pension_start", Date, nullable=False),
    Column("service_months", Integer, nullable=False),
    Column("pensionable_salary_paise", BigInteger, nullable=False),
    Column("age_at_start", Integer, nullable=False),
    Column("office_id", String(40), nullable=False),
    Column("bank_ifsc", String(11), nullable=False),
    Column("bank_account_last4", String(4), nullable=False),
    Column("original_monthly_paise", BigInteger, nullable=False),
    Column("original_rule_version", String(60), nullable=False),
    Column("original_working", Text, nullable=False),
    Column("status", String(20), nullable=False, server_default="IN_PAYMENT"),
)

# A pension recomputed under a newly published formula. Proposed automatically; an APFC (Pension) approves it
# and its arrears. Pensions in payment are never reduced, so only increases are proposed.
pension_revisions = Table(
    "pension_revisions", metadata,
    Column("revision_id", String(80), primary_key=True),
    Column("ppo_id", String(40), nullable=False, index=True),
    Column("from_rule_version", String(60), nullable=False),
    Column("to_rule_version", String(60), nullable=False),
    Column("effective_from", Date, nullable=False),
    Column("old_monthly_paise", BigInteger, nullable=False),
    Column("new_monthly_paise", BigInteger, nullable=False),
    Column("working", Text, nullable=False),
    Column("state", String(20), nullable=False),               # PROPOSED | APPROVED | REJECTED | SUPERSEDED
    Column("arrears_paise", BigInteger),                        # fixed when approved
    Column("proposed_at", DateTime(timezone=True), server_default=func.now()),
    Column("decided_by", String(80)),
    Column("decided_at", DateTime(timezone=True)),
    Column("note", Text),
)

# Mock CPPS: one monthly credit per month (paid on the last day of the month), plus arrears on a revision.
pension_payments = Table(
    "pension_payments", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("ppo_id", String(40), nullable=False, index=True),
    Column("month", String(7), nullable=False),
    Column("kind", String(10), nullable=False),                 # MONTHLY | ARREARS
    Column("amount_paise", BigInteger, nullable=False),
    Column("revision_id", String(80), nullable=False, server_default=""),   # "" for monthly credits (unique key)
    Column("paid_on", Date, nullable=False),
    UniqueConstraint("ppo_id", "month", "kind", "revision_id", name="uq_pension_payment"),
)

# Member service snapshot (synthetic) for the pension estimate, and office staff for jurisdiction.
member_service = Table(
    "member_service", metadata,
    Column("subject", String(80), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("date_of_birth", Date, nullable=False),
    Column("date_of_joining", Date, nullable=False),
    Column("date_of_exit", Date),
    Column("eps_wages_paise", BigInteger, nullable=False),
)

office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)
