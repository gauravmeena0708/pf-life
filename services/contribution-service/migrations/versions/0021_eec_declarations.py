"""Declarations under the Employees' Enrolment Campaign, 2026 (P2.26b).

Revision ID: 0021
"""
from alembic import op

from app.infra.models import EecDeclaration

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    EecDeclaration.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    EecDeclaration.__table__.drop(bind=op.get_bind(), checkfirst=True)
