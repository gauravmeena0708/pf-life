"""Internal audit and privacy requests (illustrative P2.12d)."""
from alembic import op
from sqlalchemy import inspect

from app.infra.oversight_tables import oversight_metadata
from epfo_persistence.policy import policy_metadata

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    oversight_metadata.create_all(bind=bind, checkfirst=True)
    policy_metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for name in ("privacy_requests", "internal_paras", "internal_reports", "offices", "policy_rules"):
        if name in existing:
            table = oversight_metadata.tables.get(name)
            if table is None:
                table = policy_metadata.tables[name]
            table.drop(bind=bind, checkfirst=True)
