"""Tables owned by claim-service (created by migration 0002)."""
from sqlalchemy import JSON, BigInteger, Column, Date, DateTime, Integer, MetaData, String, Table, Text, func

from app.infra.models import IdType

metadata = MetaData()

# Projection of member accounts: seeded opening balances, then kept current from ContributionPosted.v1
# and ClaimDebitPosted.v1. Claim eligibility is evaluated against this, never against another service's DB.
accounts = Table(
    "accounts", metadata,
    Column("account_link_id", String(40), primary_key=True),
    Column("member_subject", String(80), index=True),
    Column("establishment_id", String(40), nullable=False),
    Column("office_id", String(40), nullable=False),
    Column("date_of_joining", Date, nullable=False),
    Column("date_of_exit", Date),
    Column("employee_paise", BigInteger, nullable=False, server_default="0"),
    Column("employer_paise", BigInteger, nullable=False, server_default="0"),
)

# Office staff directory (synthetic seed): which office an officer acts for.
office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
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
