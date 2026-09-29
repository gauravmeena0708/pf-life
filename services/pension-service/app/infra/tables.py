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
    Column("status", String(20), nullable=False, server_default="IN_PAYMENT"),   # IN_PAYMENT | SUSPENDED | STOPPED
    Column("status_reason", Text),
    Column("life_certificate_valid_till", Date),
    Column("life_certificate_source", String(30)),              # JEEVAN_PRAMAAN | PHYSICAL | SEED
    Column("life_certificate_ref", String(40)),                 # Pramaan ID or the office's reference
    Column("declarations", JSON),                                # latest non-remarriage / non-employment declarations
)

# Office updation activities on a pension (Pension > Track Claim Updation Activity Status): some come from the
# PRO counter (physical life certificate, death, spouse remarriage), others the DA (Pension) starts (basic details,
# pension start / stop, DLC revalidation, unhold transactions). The DA initiates, the APFC (Pension) settles.
updation_activities = Table(
    "updation_activities", metadata,
    Column("activity_id", String(40), primary_key=True),
    Column("ppo_id", String(40), nullable=False, index=True),
    Column("activity", String(30), nullable=False),
    Column("mode", String(10), nullable=False),                 # PHYSICAL | ONLINE
    Column("status", String(20), nullable=False),               # NEW | PENDING | SETTLED | REJECTED | SENT_BACK_TO_DA
    Column("details", JSON, nullable=False),
    Column("initiated_by", String(80), nullable=False),
    Column("initiated_role", String(60), nullable=False),
    Column("decided_by", String(80)),
    Column("decision_note", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
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
    Column("office_id", String(40)),
    Column("uan", String(12)),
    Column("account_link_id", String(40)),
)

office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

# Pension settlement (Form 10D): member applies → DA (Accounts) Input Data Sheet → AO approves → DA (Pension)
# worksheet → APFC (Pension) approves → DA (Pension) issues the PPO → initial arrear DA (P) → SS (P) → APFC (P)
# e-signs the PPO (approving the arrear) → DA (Pension) dispatches; the pension is then in payment.
pension_claims = Table(
    "pension_claims", metadata,
    Column("claim_id", String(40), primary_key=True),
    Column("member_subject", String(80), nullable=False, index=True),
    Column("uan", String(12), nullable=False),
    Column("name", String(120), nullable=False),
    Column("date_of_birth", Date, nullable=False),
    Column("account_link_id", String(40)),
    Column("office_id", String(40), nullable=False),
    Column("pension_from", Date, nullable=False),
    Column("state", String(30), nullable=False),
    Column("service_months", Integer, nullable=False),
    Column("aggregated", JSON, nullable=False),               # past service added by the DA (Pension)
    Column("pensionable_salary_paise", BigInteger, nullable=False),
    Column("ids", JSON),                                      # Input Data Sheet
    Column("worksheet", JSON),                                # the pension worked out under the rules in force
    Column("ppo_id", String(40)),
    Column("arrears", JSON),                                  # initial arrear: proposed, checked
    Column("history", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

scheme_certificates = Table(
    "scheme_certificates", metadata,
    Column("cert_id", String(40), primary_key=True),
    Column("member_subject", String(80), nullable=False, index=True),
    Column("uan", String(12), nullable=False),
    Column("service_months", Integer, nullable=False),
    Column("pensionable_salary_paise", BigInteger, nullable=False),
    Column("state", String(20), nullable=False),              # ISSUED | SURRENDERED | CANCELLED
    Column("surrender_purpose", String(30)),
    Column("issued_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    Column("adjudicated_by", String(80)),
)

# CPPS: a monthly disbursement run sent to the (mock) sponsor bank, its paid statement, and the office's BRS.
disbursement_runs = Table(
    "disbursement_runs", metadata,
    Column("run_id", String(40), primary_key=True),
    Column("month", String(7), nullable=False, unique=True),
    Column("state", String(20), nullable=False),              # SENT | STATEMENT_RECEIVED | RECONCILED
    Column("lines", JSON, nullable=False),                    # [{ppo_id, amount_paise, status}]
    Column("total_paise", BigInteger, nullable=False),
    Column("paid_total_paise", BigInteger),
    Column("exceptions", JSON),
    Column("created_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

brs_statements = Table(
    "brs_statements", metadata,
    Column("brs_id", String(40), primary_key=True),
    Column("month", String(7), nullable=False),
    Column("office_id", String(40), nullable=False),
    Column("scroll_total_paise", BigInteger, nullable=False),
    Column("bank_debit_total_paise", BigInteger, nullable=False),
    Column("difference_paise", BigInteger, nullable=False),
    Column("prepared_by", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
