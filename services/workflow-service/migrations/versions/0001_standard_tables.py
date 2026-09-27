"""Standard tables: outbox, inbox, idempotency_keys, audit_local (docs/architecture.md §2.2).

Revision ID: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("aggregate_type", sa.String(60), nullable=False),
        sa.Column("aggregate_id", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_outbox_unpublished", "outbox", ["published_at", "id"])
    op.create_table(
        "inbox",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_subject", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(200), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("actor_subject", "operation", "key"),
    )
    op.create_table(
        "audit_local",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_subject", sa.String(80), nullable=False),
        sa.Column("actor_stakeholder", sa.String(60), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target_type", sa.String(60), nullable=False),
        sa.Column("target_id", sa.String(80), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
    )


def downgrade() -> None:
    for table in ("audit_local", "idempotency_keys", "inbox", "outbox"):
        op.drop_table(table)
