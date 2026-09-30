"""Joint options for pension on higher wages (Phase 2, slice 8c).

Revision ID: 0006
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import higher_pension_options

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "establishment_id" not in {c["name"] for c in sa.inspect(bind).get_columns("member_service")}:
        op.add_column("member_service", sa.Column("establishment_id", sa.String(40)))
    higher_pension_options.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("higher_pension_options")
    op.drop_column("member_service", "establishment_id")
