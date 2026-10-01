"""Principal tags and employer closure/office projection. Revision ID: 0013."""
import sqlalchemy as sa
from alembic import op

from app.infra.models import PrincipalEmployerTag

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("establishments")}
    for name, kind in (("office_id", sa.String(40)), ("closed_on", sa.Date()),
                       ("last_wage_month", sa.String(7))):
        if name not in columns:
            op.add_column("establishments", sa.Column(name, kind))
    PrincipalEmployerTag.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    PrincipalEmployerTag.__table__.drop(bind=bind, checkfirst=True)
    columns = {column["name"] for column in sa.inspect(bind).get_columns("establishments")}
    for name in ("last_wage_month", "closed_on", "office_id"):
        if name in columns:
            op.drop_column("establishments", name)
