"""Exemption projection, trust passbook cache and Form 13 legs."""
from alembic import op

from app.infra.models import ExemptedEstablishment, TransferLeg, TrustPassbookCache

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for model in (ExemptedEstablishment, TransferLeg, TrustPassbookCache):
        model.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for model in (TrustPassbookCache, TransferLeg, ExemptedEstablishment):
        model.__table__.drop(bind=bind, checkfirst=True)
