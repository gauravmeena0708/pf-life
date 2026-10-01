"""Illustrative disaster recovery drills and training sandboxes (P2.12f).

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import failover_drills, training_sandboxes
from epfo_persistence.policy import policy_rules
from app.infra.tables import rule_sets

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in (failover_drills, training_sandboxes, policy_rules):
        if table.name not in existing:
            table.create(bind=bind, checkfirst=True)
    published = bind.execute(sa.select(rule_sets.c.rule_version, rule_sets.c.effective_from,
                                       rule_sets.c.document).where(rule_sets.c.status == "PUBLISHED"))
    known = set(bind.execute(sa.select(policy_rules.c.rule_version)).scalars())
    for row in published.mappings():
        if row["rule_version"] not in known:
            bind.execute(policy_rules.insert().values(rule_version=row["rule_version"],
                                                      effective_from=row["effective_from"], document=row["document"]))


def downgrade() -> None:
    bind = op.get_bind()
    for table in (policy_rules, training_sandboxes, failover_drills):
        table.drop(bind=bind, checkfirst=True)
