"""Staging for early challan payments before ECR submission and order-safe claim facts. Revision ID: 0007."""
from alembic import op

from app.infra.tables import challan_payments

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    challan_payments.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        for col in ("office_id", "form_type", "amount_paise", "route", "submitted_at"):
            op.alter_column("claim_facts", col, nullable=True)
        op.alter_column("contribution_facts", "establishment_id", nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    challan_payments.drop(bind=bind, checkfirst=True)
