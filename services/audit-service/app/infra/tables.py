"""Tables owned by audit-service (created by migration 0002).

audit_log is append-only: database triggers reject UPDATE and DELETE, and every row carries the hash
of the previous row, so any later edit made around the triggers breaks the chain and is detectable."""
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, func, text

from app.infra.models import IdType

metadata = MetaData()

audit_log = Table(
    "audit_log", metadata,
    Column("seq", IdType, primary_key=True, autoincrement=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("event_type", String(120), nullable=False, index=True),
    Column("producer", String(60), nullable=False),
    Column("aggregate_type", String(60), nullable=False),
    Column("aggregate_id", String(80), nullable=False, index=True),
    Column("correlation_id", String(36), nullable=False, index=True),
    Column("occurred_at", String(40), nullable=False),
    Column("recorded_at", DateTime(timezone=True), server_default=func.now()),
    Column("payload", JSON, nullable=False),
    Column("prev_hash", String(64), nullable=False),
    Column("hash", String(64), nullable=False),
)

APPEND_ONLY = {
    "postgresql": [
        """CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
           BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql""",
        "CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()",
    ],
    "sqlite": [
        "CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END",
        "CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END",
    ],
}


def install_append_only(connection) -> None:
    for statement in APPEND_ONLY[connection.dialect.name]:
        connection.execute(text(statement))
