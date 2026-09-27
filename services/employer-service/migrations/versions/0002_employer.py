"""Employer-service tables.

Revision ID: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("establishments",
        sa.Column("establishment_id", sa.String(40), primary_key=True),
        sa.Column("registration_number", sa.String(40), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("office_id", sa.String(40), nullable=False),
        sa.Column("pan", sa.String(10), nullable=False),
        sa.Column("gstin", sa.String(15)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"))
    op.create_table("registration_requests",
        sa.Column("request_id", sa.String(40), primary_key=True),
        sa.Column("establishment_id", sa.String(40), nullable=False),
        sa.Column("owner_subject", sa.String(80), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("evidence", sa.JSON),
        sa.Column("result_reason", sa.String(300)),
        sa.Column("verification_ref", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("grants",
        sa.Column("grant_id", sa.String(40), primary_key=True),
        sa.Column("establishment_id", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("grants", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("granted_by", sa.String(80), nullable=False),
        sa.Column("revoked_by", sa.String(80)),
        sa.Column("revocation_reason", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_grants_subject_active", "grants", ["subject", "status"])
    op.create_table("user_directory",
        sa.Column("username", sa.String(80), primary_key=True),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("role", sa.String(60), nullable=False))


def downgrade() -> None:
    for t in ("user_directory", "grants", "registration_requests", "establishments"):
        op.drop_table(t)
