"""Order-safe claim facts: tolerate decisions arriving before submission.

Revision ID: 0006
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for col in ("office_id", "form_type", "amount_paise", "account_link_id", "route", "rule_version"):
            op.alter_column("claim_facts", col, nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for col in ("office_id", "form_type", "amount_paise", "account_link_id", "route", "rule_version"):
            op.alter_column("claim_facts", col, nullable=False)
