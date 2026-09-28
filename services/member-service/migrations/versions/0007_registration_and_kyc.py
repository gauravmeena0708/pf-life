"""Employer registration of new joinees (Form 11) and member KYC with employer approval.

Revision ID: 0007
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import kyc_requests, kyc_uploads

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("employments")}
    if "form11" not in columns:                    # 0002 builds from the current definitions on a fresh database
        op.add_column("employments", sa.Column("form11", sa.JSON))
        op.add_column("employments", sa.Column("registered_by", sa.String(80)))
    kyc_requests.create(bind=op.get_bind(), checkfirst=True)
    kyc_uploads.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    kyc_uploads.drop(bind=op.get_bind(), checkfirst=True)
    kyc_requests.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("employments", "registered_by")
    op.drop_column("employments", "form11")
