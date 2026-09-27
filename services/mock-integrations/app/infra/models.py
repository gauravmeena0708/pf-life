"""Standard tables present in every service database (docs/architecture.md §2.2)."""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# BIGINT ids in PostgreSQL; INTEGER on SQLite so tests get autoincrement.
IdType = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class Outbox(Base):
    """Events written in the same transaction as the state change; a relay publishes them."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    event_type: Mapped[str] = mapped_column(String(120))
    aggregate_type: Mapped[str] = mapped_column(String(60))
    aggregate_id: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Inbox(Base):
    """IDs of consumed events; a duplicate delivery is acknowledged and ignored."""
    __tablename__ = "inbox"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyKey(Base):
    """Stored response of a command, so a retried command returns the original result."""
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("actor_subject", "operation", "key"),)
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    actor_subject: Mapped[str] = mapped_column(String(80))
    operation: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLocal(Base):
    """This service's audit records, shipped to audit-service through the outbox."""
    __tablename__ = "audit_local"
    id: Mapped[int] = mapped_column(IdType, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_subject: Mapped[str] = mapped_column(String(80))
    actor_stakeholder: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str] = mapped_column(String(80))
    correlation_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
