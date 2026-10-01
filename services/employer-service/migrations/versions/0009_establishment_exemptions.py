"""Exemption notifications and trust identity for exempted establishments.

Revision ID: 0009
"""
from alembic import op

from app.infra.tables import establishment_exemptions

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    establishment_exemptions.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    establishment_exemptions.drop(bind=op.get_bind(), checkfirst=True)
