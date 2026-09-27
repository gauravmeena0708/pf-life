"""Read models owned by reporting-service (created by migration 0002). Built only from events."""
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table

metadata = MetaData()

grievance_facts = Table(
    "grievance_facts", metadata,
    Column("grievance_id", String(40), primary_key=True),
    Column("office_id", String(40), nullable=False, index=True),
    Column("category", String(40), nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("tier", String(4), nullable=False),
    Column("escalations", Integer, nullable=False, server_default="0"),
    Column("resolved_at", DateTime(timezone=True)),
    Column("within_sla", Boolean),
)
