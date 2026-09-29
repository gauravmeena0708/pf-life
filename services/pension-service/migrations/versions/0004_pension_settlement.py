"""Pension settlement (Form 10D to PPO), scheme certificates, CPPS runs and BRS.

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import brs_statements, disbursement_runs, pension_claims, scheme_certificates

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("member_service")}
    for name in ("office_id", "uan", "account_link_id"):
        if name not in columns:                    # 0002 builds from the current definitions on a fresh database
            op.add_column("member_service", sa.Column(name, sa.String(40)))
    for table in (pension_claims, scheme_certificates, disbursement_runs, brs_statements):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    for table in (brs_statements, disbursement_runs, scheme_certificates, pension_claims):
        table.drop(bind=op.get_bind(), checkfirst=True)
