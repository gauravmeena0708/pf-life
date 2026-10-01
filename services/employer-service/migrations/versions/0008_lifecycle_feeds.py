"""Establishment lifecycle and external registration feeds.

Revision ID: 0008
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import offices
from epfo_persistence.policy import policy_rules

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "closed_on" not in {c["name"] for c in inspector.get_columns("establishments")}:
        op.add_column("establishments", sa.Column("closed_on", sa.Date()))
    existing = {c["name"] for c in sa.inspect(bind).get_columns("registration_requests")}
    for name, size in (("source", 30), ("source_ref", 80)):
        if name not in existing:
            op.add_column("registration_requests", sa.Column(name, sa.String(size)))
    offices.create(bind=bind, checkfirst=True)
    policy_rules.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    policy_rules.drop(bind=bind, checkfirst=True)
    offices.drop(bind=bind, checkfirst=True)
    for table, names in (("registration_requests", ("source_ref", "source")), ("establishments", ("closed_on",))):
        existing = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        for name in names:
            if name in existing:
                op.drop_column(table, name)
