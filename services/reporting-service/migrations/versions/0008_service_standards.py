"""Seed the published citizen's charter standards. Revision ID: 0008."""
import sqlalchemy as sa
from alembic import op

from app.domain.standards import CHARTER_STANDARDS
from app.infra.tables import service_standards

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    service_standards.create(bind=bind, checkfirst=True)
    columns = {column["name"] for column in sa.inspect(bind).get_columns("service_standards")}
    if {"code", "name", "days", "basis", "source"} <= columns:
        for standard in CHARTER_STANDARDS:
            exists = bind.execute(sa.select(service_standards.c.code).where(
                service_standards.c.code == standard["code"])).first()
            if exists is None:
                bind.execute(service_standards.insert().values(**standard))


def downgrade() -> None:
    service_standards.drop(bind=op.get_bind(), checkfirst=True)
