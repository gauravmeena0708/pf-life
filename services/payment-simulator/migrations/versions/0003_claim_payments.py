"""Payment intents also carry claim settlements (Journey B6).

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("payment_intents", "trrn", existing_type=sa.String(20), nullable=True)
    op.add_column("payment_intents", sa.Column("purpose", sa.String(20), nullable=False, server_default="CHALLAN"))
    op.add_column("payment_intents", sa.Column("reference_id", sa.String(40)))


def downgrade() -> None:
    op.drop_column("payment_intents", "reference_id")
    op.drop_column("payment_intents", "purpose")
    op.alter_column("payment_intents", "trrn", existing_type=sa.String(20), nullable=False)
