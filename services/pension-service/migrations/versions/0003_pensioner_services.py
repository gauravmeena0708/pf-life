"""Life certificates, suspension and resumption, declarations and office updation activities.

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import updation_activities

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("pensioners")}
    for name, kind in (("status_reason", sa.Text), ("life_certificate_valid_till", sa.Date), ("life_certificate_source", sa.String(30)),
                       ("life_certificate_ref", sa.String(40)), ("declarations", sa.JSON)):
        if name not in columns:                    # 0002 builds from the current definitions on a fresh database
            op.add_column("pensioners", sa.Column(name, kind))
    updation_activities.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    updation_activities.drop(bind=op.get_bind(), checkfirst=True)
    for name in ("declarations", "life_certificate_ref", "life_certificate_source", "life_certificate_valid_till", "status_reason"):
        op.drop_column("pensioners", name)
