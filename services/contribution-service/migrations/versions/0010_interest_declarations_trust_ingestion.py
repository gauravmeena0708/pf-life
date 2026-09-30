"""Recorded interest rates and surrendered-trust ingestions (Phase 2, slice 8d).

Revision ID: 0010
"""
import sqlalchemy as sa
from alembic import op

from app.infra.models import InterestRateDeclaration, PastAccumulationIngestion

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "exemption_status" not in {c["name"] for c in sa.inspect(bind).get_columns("establishments")}:
        op.add_column("establishments", sa.Column("exemption_status", sa.String(30)))
    InterestRateDeclaration.__table__.create(bind=bind, checkfirst=True)
    PastAccumulationIngestion.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    PastAccumulationIngestion.__table__.drop(bind=op.get_bind(), checkfirst=True)
    InterestRateDeclaration.__table__.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("establishments", "exemption_status")
