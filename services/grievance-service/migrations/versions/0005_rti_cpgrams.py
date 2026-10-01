"""RTI office register and CPGRAMS external reference.

Revision ID: 0005
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import rti_requests

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("grievances")}
    if "cpgrams_registration_no" not in columns:
        op.add_column("grievances", sa.Column("cpgrams_registration_no", sa.String(80)))
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("grievances")}
    if "uq_grievances_cpgrams_registration_no" not in indexes:
        op.create_index("uq_grievances_cpgrams_registration_no", "grievances", ["cpgrams_registration_no"], unique=True)
    rti_requests.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    rti_requests.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_index("uq_grievances_cpgrams_registration_no", table_name="grievances")
    op.drop_column("grievances", "cpgrams_registration_no")
