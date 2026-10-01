"""Synthetic exemption directory and trust Annexure K requests."""
from alembic import op

from app.infra.tables import annexure_k_requests, exempted_establishments

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exempted_establishments.create(bind=bind, checkfirst=True)
    annexure_k_requests.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    annexure_k_requests.drop(bind=bind, checkfirst=True)
    exempted_establishments.drop(bind=bind, checkfirst=True)
