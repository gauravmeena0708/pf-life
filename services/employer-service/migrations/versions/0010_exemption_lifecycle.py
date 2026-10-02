"""Trust audits and exemption proceedings.

Revision ID: 0010
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import (establishment_exemptions, exemption_proceeding_steps,
                              exemption_proceedings, offices, trust_audits)

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, definition in ((offices, "zone_id", sa.Column("zone_id", sa.String(40))),
                                      (establishment_exemptions, "ended_on", sa.Column("ended_on", sa.Date()))):
        if column not in {c["name"] for c in sa.inspect(bind).get_columns(table.name)}:
            op.add_column(table.name, definition)
    for table in (trust_audits, exemption_proceedings, exemption_proceeding_steps):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (exemption_proceeding_steps, exemption_proceedings, trust_audits):
        table.drop(bind=bind, checkfirst=True)
    for table, column in ((establishment_exemptions, "ended_on"), (offices, "zone_id")):
        if column in {c["name"] for c in sa.inspect(bind).get_columns(table.name)}:
            op.drop_column(table.name, column)
