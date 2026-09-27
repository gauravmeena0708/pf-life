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
