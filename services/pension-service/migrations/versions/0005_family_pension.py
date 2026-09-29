"""Family pension (Phase 2, slice 6b): the kind of a pension claim, the family on record.

Revision ID: 0005
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import family_members

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pension_claims", sa.Column("kind", sa.String(10), nullable=False, server_default="MEMBER"))
    op.add_column("pension_claims", sa.Column("family", sa.JSON()))
    family_members.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    family_members.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("pension_claims", "family")
    op.drop_column("pension_claims", "kind")
