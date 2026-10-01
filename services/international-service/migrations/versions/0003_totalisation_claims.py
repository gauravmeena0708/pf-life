"""Persist routed totalisation claims.

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import totalisation_claims

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(totalisation_claims.name):
        totalisation_claims.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(totalisation_claims.name):
        totalisation_claims.drop(bind=bind, checkfirst=True)
