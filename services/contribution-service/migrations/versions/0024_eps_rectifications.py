"""Rectification of erroneous EPS contributions (P2.19c, HO circular WSU/2025/E-961539).

Revision ID: 0024
"""
from alembic import op

from app.infra.models import EpsIneligibleMember, EpsRectification

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for model in (EpsRectification, EpsIneligibleMember):
        model.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for model in (EpsIneligibleMember, EpsRectification):
        model.__table__.drop(bind=op.get_bind(), checkfirst=True)
