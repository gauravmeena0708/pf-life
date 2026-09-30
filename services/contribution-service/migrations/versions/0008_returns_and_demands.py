"""Returns and payments (Phase 2, slice 7a): direct challans (no filing), their kind and knocked-off amount;
demands for late payment (14B / 7Q) and knock-offs.

Revision ID: 0008
"""
import sqlalchemy as sa
from alembic import op

from app.infra.models import Demand, KnockOff

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("challans", "filing_id", nullable=True)
    op.add_column("challans", sa.Column("kind", sa.String(20), nullable=False, server_default="ECR"))
    op.add_column("challans", sa.Column("applied_paise", sa.BigInteger(), nullable=False, server_default="0"))
    Demand.__table__.create(bind=op.get_bind(), checkfirst=True)
    KnockOff.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    KnockOff.__table__.drop(bind=op.get_bind(), checkfirst=True)
    Demand.__table__.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("challans", "applied_paise")
    op.drop_column("challans", "kind")
    op.alter_column("challans", "filing_id", nullable=False)
