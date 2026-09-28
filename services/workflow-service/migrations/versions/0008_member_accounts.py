"""Member accounts for checking process forms (exit, transfer).

Revision ID: 0008
"""
from alembic import op

from app.infra.tables import member_accounts

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    member_accounts.create(bind=op.get_bind(), checkfirst=True)     # 0002 may already have built it


def downgrade() -> None:
    member_accounts.drop(bind=op.get_bind(), checkfirst=True)
