"""Tables owned by intelligence-service (created by migration 0002)."""
from sqlalchemy import JSON, BigInteger, Column, DateTime, MetaData, String, Table, Text, func

from app.infra.models import IdType

metadata = MetaData()

# What the risk rules look at: security events only (never claim content or member data).
security_events = Table(
    "security_events", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("subject", String(80), nullable=False, index=True),
    Column("event_type", String(40), nullable=False),
    Column("device", String(64), nullable=False, index=True),
    Column("at", DateTime(timezone=True), nullable=False),
)

risk_signals = Table(
    "risk_signals", metadata,
    Column("signal_id", String(40), primary_key=True),
    Column("subject", String(80), nullable=False, index=True),
    Column("detection_type", String(60), nullable=False),
    Column("rule_version", String(40), nullable=False),
    Column("evidence_refs", JSON, nullable=False),
    Column("explanation", Text, nullable=False),
    Column("context", JSON, nullable=False),                  # facts shown to the reviewer that are NOT evidence
    Column("status", String(30), nullable=False),             # OPEN | NEEDS_MORE_EVIDENCE | CONFIRMED | BENIGN
    Column("review_note", Text),
    Column("reviewer_subject", String(80)),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

# ── AI (Journey E) ────────────────────────────────────────────────────────────────────────────────

# What the officer-facing analysis may use about a claim: facts from events only, no member identity.
claim_facts = Table(
    "claim_facts", metadata,
    Column("claim_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False),
    Column("form_type", String(10), nullable=False),
    Column("amount_paise", BigInteger, nullable=False),
    Column("account_link_id", String(40), nullable=False),
    Column("route", String(10), nullable=False),
    Column("advisory_signal_id", String(40)),
    Column("rule_version", String(40), nullable=False),
    Column("decisions", JSON, nullable=False),
)

grievance_links = Table(
    "grievance_links", metadata,
    Column("grievance_id", String(40), primary_key=True),
    Column("linked_claim_id", String(40), index=True),
    Column("category", String(40), nullable=False),
)

office_staff = Table(
    "office_staff", metadata,
    Column("subject", String(80), primary_key=True),
    Column("stakeholder", String(60), nullable=False),
    Column("office_id", String(40), nullable=False),
)

# Metadata of every AI answer: who asked, which mode and model, which paragraphs were used. Never the raw
# prompt or the model's reasoning (init.md §8.3).
ai_interactions = Table(
    "ai_interactions", metadata,
    Column("interaction_id", String(40), primary_key=True),
    Column("actor_subject", String(80), nullable=False),
    Column("stakeholder", String(60), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("mode", String(20), nullable=False),
    Column("model_id", String(80), nullable=False),
    Column("retrieval_refs", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

ai_feedback = Table(
    "ai_feedback", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("interaction_id", String(40), nullable=False, index=True),
    Column("actor_subject", String(80), nullable=False),
    Column("rating", String(20), nullable=False),
    Column("correction", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
