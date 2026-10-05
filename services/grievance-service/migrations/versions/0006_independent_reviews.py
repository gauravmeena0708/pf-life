"""P2.24 illustrative independent grievance reviews.

Revision ID: 0006
"""
from alembic import op

from app.infra.tables import grievance_reviews

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    grievance_reviews.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    grievance_reviews.drop(bind=op.get_bind(), checkfirst=True)
