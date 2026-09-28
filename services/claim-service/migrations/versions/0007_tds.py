"""TDS on withdrawals under the policy in force on the payment date, and Form 15G / 15H declarations.

Revision ID: 0007
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import tax_declarations

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "tax" not in {c["name"] for c in sa.inspect(bind).get_columns("claims")}:     # 0002 builds from the current definitions
        op.add_column("claims", sa.Column("tax", sa.JSON))
    if "pan_verified" not in {c["name"] for c in sa.inspect(bind).get_columns("accounts")}:
        op.add_column("accounts", sa.Column("pan_verified", sa.Boolean, nullable=False, server_default=sa.false()))
    tax_declarations.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    tax_declarations.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("accounts", "pan_verified")
    op.drop_column("claims", "tax")
