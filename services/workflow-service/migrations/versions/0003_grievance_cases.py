"""Cases also track grievances (Journey C): a case has either a claim or a grievance.

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("cases", "claim_id", existing_type=sa.String(40), nullable=True)
    op.add_column("cases", sa.Column("grievance_id", sa.String(40), unique=True))


def downgrade() -> None:
    op.drop_column("cases", "grievance_id")
    op.alter_column("cases", "claim_id", existing_type=sa.String(40), nullable=False)
