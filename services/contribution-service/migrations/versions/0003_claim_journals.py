"""Journals may belong to a claim or an opening balance instead of an ECR filing (Journey B6).

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002_contribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("journals", "filing_id", existing_type=sa.String(36), nullable=True)
    op.add_column("journals", sa.Column("claim_id", sa.String(40)))


def downgrade() -> None:
    op.drop_column("journals", "claim_id")
    op.alter_column("journals", "filing_id", existing_type=sa.String(36), nullable=False)
