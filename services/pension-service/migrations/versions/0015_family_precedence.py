"""P2.19: dependent parents, EPS nominees and death dates for family precedence."""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("family_members")}
    if "dependent" not in columns:
        op.add_column("family_members", sa.Column("dependent", sa.Boolean, nullable=False, server_default=sa.false()))
    if "nomination_valid" not in columns:
        op.add_column("family_members", sa.Column("nomination_valid", sa.Boolean, nullable=False, server_default=sa.false()))
    if "date_of_death" not in columns:
        op.add_column("family_members", sa.Column("date_of_death", sa.Date))
    if "evidence_ref" not in columns:
        op.add_column("family_members", sa.Column("evidence_ref", sa.String(120)))


def downgrade():
    op.drop_column("family_members", "evidence_ref")
    op.drop_column("family_members", "date_of_death")
    op.drop_column("family_members", "nomination_valid")
    op.drop_column("family_members", "dependent")
