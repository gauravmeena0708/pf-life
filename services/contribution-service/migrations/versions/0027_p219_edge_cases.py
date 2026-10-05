"""P2.19 SCWF member transfers and establishment amalgamations."""
from alembic import op

from app.infra.models import EstablishmentMerger, ScwfTransfer

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ScwfTransfer.__table__.create(bind=bind, checkfirst=True)
    EstablishmentMerger.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    EstablishmentMerger.__table__.drop(bind=bind, checkfirst=True)
    ScwfTransfer.__table__.drop(bind=bind, checkfirst=True)
