"""Order-safe transfer legs: separate eps_detail column to prevent read-modify-write overwrite."""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    if "eps_detail" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("transfer_legs")}:
        op.add_column("transfer_legs", sa.Column("eps_detail", sa.JSON, nullable=True))


def downgrade():
    op.drop_column("transfer_legs", "eps_detail")
