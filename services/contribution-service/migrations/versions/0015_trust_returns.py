"""Exempt trust monthly returns, evaluator and priority matrix."""
from alembic import op

from app.infra.models import TrustFlag, TrustReturn

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for model in (TrustReturn, TrustFlag):
        model.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for model in (TrustFlag, TrustReturn):
        model.__table__.drop(bind=bind, checkfirst=True)
