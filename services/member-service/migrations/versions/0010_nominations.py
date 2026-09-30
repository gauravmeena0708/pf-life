"""e-Nomination (Form 2) (Phase 2, slice 8b).

Revision ID: 0010
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import nominations

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("nominations"):
        nominations.create(op.get_bind())


def downgrade() -> None:
    op.drop_table("nominations")
