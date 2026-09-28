"""Tables owned by workflow-service (created by migration 0002)."""
from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, MetaData, String, Table, Text, func

from app.infra.models import IdType

metadata = MetaData()

offices = Table(
    "offices", metadata,
    Column("office_id", String(40), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("zone_id", String(40)),
    Column("member_subject", String(80), index=True),        # who may start a self-service process about it
    Column("establishment_id", String(40)),                  # whose employer may attest
)

# Who is posted where, in which role (synthetic seed; HRM postings are phase 2).
office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("username", String(80), nullable=False),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

# One case per claim. `chain` is the approval chain for the claim's amount band; `step` points at the
# role whose turn it is. After the last approver the case waits for the cash section (fo.cash).
cases = Table(
    "cases", metadata,
    Column("case_id", String(40), primary_key=True),
    Column("claim_id", String(40), unique=True),             # set for claim cases
    Column("grievance_id", String(40), unique=True),         # set for grievance cases
    Column("advisory_signal_id", String(40)),                # an open advisory risk signal the officer should see
    Column("process", String(60)),                           # tier-2 process name (ADR-0005), for engine cases
    Column("subject_ref", String(40), index=True),           # what the process is about, e.g. a UAN
    Column("data", JSON),                                    # engine cases: the form data that routes the case
    Column("office_id", String(40), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("form_type", String(10), nullable=False),
    Column("account_link_id", String(40), nullable=False),
    Column("amount_paise", BigInteger, nullable=False),
    Column("rule_version", String(40), nullable=False),
    Column("chain", JSON, nullable=False),
    Column("step", Integer, nullable=False, server_default="0"),
    Column("round", Integer, nullable=False, server_default="1"),
    Column("state", String(40), nullable=False),     # AUTO_PENDING | IN_REVIEW | AWAITING_PAYMENT | PAYMENT_ISSUED | PAYMENT_RETURNED | OPEN (grievance) | CLOSED | REJECTED
    Column("current_role", String(60)),
    Column("assignee_subject", String(80)),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("sla_due_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

case_actions = Table(
    "case_actions", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("case_id", String(40), nullable=False, index=True),
    Column("round", Integer, nullable=False),
    Column("at", DateTime(timezone=True), server_default=func.now()),
    Column("officer_subject", String(80), nullable=False),
    Column("officer_role", String(60), nullable=False),
    Column("action", String(40), nullable=False),
    Column("approval_level", Integer),
    Column("reason", Text),
    Column("checks", JSON),
)

# Which office a process subject belongs to (synthetic seed), so the engine can enforce jurisdiction.
subject_offices = Table(
    "subject_offices", metadata,
    Column("subject_ref", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False),
    Column("zone_id", String(40)),
    Column("member_subject", String(80), index=True),        # who may start a self-service process about it
    Column("establishment_id", String(40)),                  # whose employer may attest
)
