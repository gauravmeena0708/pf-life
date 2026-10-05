"""P2.19: a principal employer's recoveries from a vanished contractor (EPF Act s.8A)."""
from alembic import op

from app.infra.tables import contractor_recoveries

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    contractor_recoveries.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    contractor_recoveries.drop(bind=bind, checkfirst=True)

