"""Annual interest crediting under the rate declared in the policy rule set.

Revision ID: 0005
"""
from alembic import op

from app.infra.models import InterestPosting

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    InterestPosting.__table__.create(bind=op.get_bind(), checkfirst=True)    # 0002 may already have built it


def downgrade() -> None:
    InterestPosting.__table__.drop(bind=op.get_bind(), checkfirst=True)
