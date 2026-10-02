"""PMVBRY paid ECR projection, choices, literacy and mock disbursements."""
import sqlalchemy as sa
from alembic import op
from app.infra.models import PmvbryEstablishment, PmvbryEcrRow, PmvbryLiteracy, PmvbryPayment

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None

TABLES = (PmvbryEstablishment.__table__, PmvbryEcrRow.__table__, PmvbryLiteracy.__table__, PmvbryPayment.__table__)

def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in TABLES:
        if table.name not in existing:
            table.create(op.get_bind(), checkfirst=True)

def downgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in reversed(TABLES):
        if table.name in existing:
            table.drop(op.get_bind(), checkfirst=True)
