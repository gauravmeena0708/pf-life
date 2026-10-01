"""Face allotment, UAN activation and inoperative account verification (P2.12a).

Revision ID: 0013
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import crowdsource_verifications
from epfo_persistence.policy import policy_rules

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "activated_at" not in {c["name"] for c in sa.inspect(bind).get_columns("members")}:
        op.add_column("members", sa.Column("activated_at", sa.DateTime(timezone=True)))
    if not sa.inspect(bind).has_table("crowdsource_verifications"):
        crowdsource_verifications.create(bind, checkfirst=True)
    if not sa.inspect(bind).has_table("policy_rules"):
        policy_rules.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("crowdsource_verifications"):
        op.drop_table("crowdsource_verifications")
    if sa.inspect(bind).has_table("policy_rules"):
        op.drop_table("policy_rules")
    if "activated_at" in {c["name"] for c in sa.inspect(bind).get_columns("members")}:
        op.drop_column("members", "activated_at")
