"""Inoperative verification, reactivation and short-lived public search references.

Revision ID: 0012
"""
from alembic import op

from app.infra.models import AccountReactivation, InoperativeSearchRef, InoperativeVerification

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for model in (InoperativeVerification, AccountReactivation, InoperativeSearchRef):
        model.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for model in (InoperativeSearchRef, AccountReactivation, InoperativeVerification):
        model.__table__.drop(bind=bind, checkfirst=True)
