"""Tables owned by compliance-service (Phase 2, slice 8a)."""
from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, func

metadata = MetaData()

# Office postings and establishment names (synthetic seed) — jurisdiction, and the public defaulter list.
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

# A compliance case: proceedings against an establishment for not filing, not paying, or damages.
compliance_cases = Table(
    "compliance_cases", metadata,
    Column("case_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("kind", String(30), nullable=False),               # NON_FILING | NON_PAYMENT | LATE_PAYMENT_DAMAGES | OTHER
    Column("wage_months", JSON, nullable=False),
    Column("amount_paise", BigInteger, nullable=False, server_default="0"),
    Column("state", String(20), nullable=False),              # OPEN | CLOSED
    Column("history", JSON, nullable=False),
    Column("opened_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# 14B / 7Q demands as contribution-service publishes them (DemandStateChanged.v1).
demands = Table(
    "demands", metadata,
    Column("demand_id", String(60), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("kind", String(20), nullable=False),
    Column("trrn", String(20)),
    Column("wage_month", String(7)),
    Column("amount_paise", BigInteger, nullable=False),
    Column("days_late", Integer, nullable=False, server_default="0"),
    Column("state", String(20), nullable=False),
    Column("working", Text),
    Column("source_at", DateTime(timezone=True)),   # when contribution-service changed it: an older event never overwrites a newer state
)

# VISHWAS: settling disputed 14B damages (illustrative share in the rules).
vishwas_applications = Table(
    "vishwas_applications", metadata,
    Column("application_id", String(40), primary_key=True),
    Column("establishment_id", String(40), nullable=False, index=True),
    Column("demand_ids", JSON, nullable=False),
    Column("damages_paise", BigInteger, nullable=False),
    Column("revised_paise", BigInteger),
    Column("state", String(20), nullable=False),              # SUBMITTED | APPROVED | REJECTED
    Column("submitted_by", String(80), nullable=False),
    Column("decided_by", String(80)),
    Column("decision_note", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

compliance_officers = Table(
    "compliance_officers", metadata,
    Column("subject", String(80), primary_key=True), Column("rank", String(20), nullable=False),
    Column("office_id", String(40), nullable=False), Column("barred", Boolean, nullable=False, server_default="0"),
)

inspections = Table(
    "inspections", metadata,
    Column("inspection_id", String(40), primary_key=True), Column("establishment_id", String(40), nullable=False),
    Column("office_id", String(40), nullable=False), Column("eo_subject", String(80), nullable=False),
    Column("circle_officer", String(80), nullable=False), Column("purpose", String(30), nullable=False),
    Column("period_from", String(7), nullable=False), Column("period_to", String(7), nullable=False),
    Column("signal_id", String(80)), Column("note", Text, nullable=False), Column("state", String(30), nullable=False),
    Column("report", JSON), Column("decision", String(20)), Column("due_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

inspection_steps = Table(
    "inspection_steps", metadata,
    Column("step_id", String(40), primary_key=True), Column("inspection_id", String(40), nullable=False),
    Column("stage", String(20), nullable=False), Column("actor_subject", String(80), nullable=False),
    Column("note", Text), Column("detail", JSON), Column("due_at", DateTime(timezone=True)),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

inquiries = Table(
    "inquiries", metadata,
    Column("case_id", String(40), primary_key=True), Column("diary_no", String(80), unique=True, nullable=False),
    Column("office_id", String(40), nullable=False), Column("establishment_id", String(40), nullable=False),
    Column("dispute", String(20), nullable=False), Column("period_from", String(7), nullable=False),
    Column("period_to", String(7), nullable=False), Column("inspection_id", String(40)),
    Column("contributory_uans", Integer, nullable=False), Column("officer_rank", String(20), nullable=False),
    Column("officer_subject", String(80), nullable=False), Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("registration_due_at", DateTime(timezone=True)), Column("concluded_on", DateTime(timezone=True)),
    Column("order_due_at", DateTime(timezone=True)), Column("state", String(20), nullable=False),
    # P2.11b: 7A / 7C / 14B; the case a 7C reopens; the auto-calculated 14B / 7Q demands a 14B case covers; the order
    Column("section", String(4), nullable=False, server_default="7A"), Column("parent_case_id", String(40)),
    Column("demand_ids", JSON), Column("ordered_at", DateTime(timezone=True)), Column("ex_parte", Boolean),
    Column("order_demand_ids", JSON),
)

inquiry_actions = Table(
    "inquiry_actions", metadata,
    Column("action_id", String(40), primary_key=True), Column("case_id", String(40), nullable=False),
    Column("kind", String(30), nullable=False), Column("actor_subject", String(80), nullable=False),
    Column("detail", JSON, nullable=False), Column("occurred_at", DateTime(timezone=True), nullable=False),
)

# P2.11c: the legal case register (appeals under 7-I with the 7-O pre-deposit, writs, prosecutions in court) and prosecutions
legal_cases = Table(
    "legal_cases", metadata,
    Column("legal_case_id", String(40), primary_key=True), Column("office_id", String(40), nullable=False),
    Column("establishment_id", String(40), nullable=False), Column("kind", String(30), nullable=False),      # APPEAL_7I | WRIT | PROSECUTION | NCLT | OTHER
    Column("forum", String(120), nullable=False), Column("case_no", String(80)), Column("filed_on", String(10), nullable=False),
    Column("inquiry_case_id", String(40)), Column("impugned_demand_ids", JSON), Column("amount_paise", BigInteger),
    Column("pre_deposit_percent", Integer), Column("pre_deposits", JSON), Column("delay_condonation", Boolean),
    Column("stayed", Boolean, nullable=False, server_default="0"), Column("state", String(20), nullable=False),     # PENDING | DECIDED
    Column("orders", JSON, nullable=False), Column("note", Text), Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

prosecutions = Table(
    "prosecutions", metadata,
    Column("prosecution_id", String(40), primary_key=True), Column("office_id", String(40), nullable=False),
    Column("establishment_id", String(40), nullable=False), Column("inquiry_case_id", String(40)),
    Column("offence", String(30), nullable=False), Column("particulars", Text, nullable=False),
    Column("state", String(20), nullable=False),      # SCN_ISSUED | REPLIED | SANCTIONED | COMPLAINT_FILED | DROPPED
    Column("scn_at", DateTime(timezone=True), nullable=False), Column("reply_due", DateTime(timezone=True), nullable=False),
    Column("history", JSON, nullable=False), Column("legal_case_id", String(40)), Column("created_by", String(80), nullable=False),
)

# P2.11d: recovery under s.8B-8G (Recovery Manual): the certificate, its execution and what it realised
recovery_cases = Table(
    "recovery_cases", metadata,
    Column("recovery_case_id", String(40), primary_key=True), Column("office_id", String(40), nullable=False),
    Column("establishment_id", String(40), nullable=False), Column("inquiry_case_id", String(40)), Column("certificate_no", String(60), nullable=False),
    Column("demand_ids", JSON, nullable=False), Column("amount_paise", BigInteger, nullable=False),
    Column("realised_paise", BigInteger, nullable=False, server_default="0"),
    Column("state", String(20), nullable=False),        # CERTIFIED | NOTICE_SERVED | IN_EXECUTION | INSTALMENTS | CLOSED
    Column("recovery_officer", String(80), nullable=False), Column("issued_by", String(80), nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False), Column("pay_by", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
)

recovery_actions = Table(
    "recovery_actions", metadata,
    Column("action_id", String(40), primary_key=True), Column("recovery_case_id", String(40), nullable=False, index=True),
    Column("kind", String(30), nullable=False), Column("detail", JSON, nullable=False),
    Column("actor_subject", String(80), nullable=False), Column("occurred_at", DateTime(timezone=True), nullable=False),
)
