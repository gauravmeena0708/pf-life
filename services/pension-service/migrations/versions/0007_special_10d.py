"""Special Form 10D reconstruction cases."""
from alembic import op

from app.infra.tables import special_10d_cases

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    special_10d_cases.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    special_10d_cases.drop(bind=op.get_bind(), checkfirst=True)
