"""EPS pensioners, for re-employment (P2.19).

Revision ID: 0023
"""
from alembic import op

from app.infra.models import EpsPensioner

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    EpsPensioner.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    EpsPensioner.__table__.drop(bind=op.get_bind(), checkfirst=True)
