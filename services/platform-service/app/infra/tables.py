"""Tables owned by platform-service (created by migration 0002): rule-set versions for policy administration."""
from sqlalchemy import JSON, Column, Date, DateTime, Integer, MetaData, String, Table, Text, func

metadata = MetaData()

# One row per rule-set version. DRAFT → SUBMITTED → PUBLISHED (or back to DRAFT when returned).
# Published rows are never edited; a change is a new version with a later effective date.
rule_sets = Table(
    "rule_sets", metadata,
    Column("version_id", String(40), primary_key=True),
    Column("rule_version", String(60), nullable=False, unique=True),
    Column("effective_from", Date, nullable=False),
    Column("status", String(20), nullable=False),
    Column("document", JSON, nullable=False),
    Column("base_version_id", String(40)),
    Column("change_note", Text, nullable=False),
    Column("drafted_by", String(80), nullable=False),
    Column("submitted_by", String(80)),
    Column("decided_by", String(80)),
    Column("decision_note", Text),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("submitted_at", DateTime(timezone=True)),
    Column("decided_at", DateTime(timezone=True)),
)

# The NDC Issue Tracker (P2.8e): an office raises a block / unblock with the order; the IS Division executes it.
issue_tracker_requests = Table(
    "issue_tracker_requests", metadata,
    Column("request_id", String(40), primary_key=True),
    Column("kind", String(30), nullable=False),               # FREEZE_MEMBER | DEFREEZE_MEMBER | LOGIN_NOTICE
    Column("target_uan", String(12), nullable=False),
    Column("order_ref", String(80), nullable=False),
    Column("order_document", JSON),                           # {filename, size_bytes, sha256}
    Column("reason", Text, nullable=False),
    Column("notice", Text),                                   # the message a login notice shows
    Column("state", String(20), nullable=False),              # RAISED | EXECUTED | REJECTED
    Column("raised_by", String(80), nullable=False),
    Column("raised_role", String(60), nullable=False),
    Column("raised_at", DateTime(timezone=True), server_default=func.now()),
    Column("executed_by", String(80)),
    Column("executed_at", DateTime(timezone=True)),
    Column("execution_note", Text),
)
