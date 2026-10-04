"""P2.21b: deaths from the civil registry and documents issued to DigiLocker."""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import death_registrations, digilocker_documents

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in (death_registrations, digilocker_documents):
        if not sa.inspect(bind).has_table(table.name):
            table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (digilocker_documents, death_registrations):
        if sa.inspect(bind).has_table(table.name):
            table.drop(bind, checkfirst=True)
