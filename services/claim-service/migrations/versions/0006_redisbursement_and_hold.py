"""Re-disbursement after a bank return, and holding claims while an account is frozen (init.md §7).

Revision ID: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("claims")}
    if "prior_state" in columns:                 # 0002 builds from the current definitions on a fresh database
        return
    op.add_column("claims", sa.Column("prior_state", sa.String(40)))
    op.add_column("claims", sa.Column("recommended", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("claims", sa.Column("payee_ifsc", sa.String(11)))
    op.add_column("claims", sa.Column("payee_account_last4", sa.String(4)))


def downgrade() -> None:
    for column in ("payee_account_last4", "payee_ifsc", "recommended", "prior_state"):
        op.drop_column("claims", column)
