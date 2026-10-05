"""P2.24: Authorised representatives table."""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import representatives

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(representatives.name):
        representatives.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(representatives.name):
        representatives.drop(bind, checkfirst=True)
