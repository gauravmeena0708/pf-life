"""Legal case register and prosecutions (P2.11c).

Revision ID: 0006
"""
from alembic import op

from app.infra.tables import legal_cases, prosecutions

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (legal_cases, prosecutions):
        table.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (prosecutions, legal_cases):
        table.drop(bind=op.get_bind(), checkfirst=True)
