"""Project the exemption end date."""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    if "ended_on" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("exempted_establishments")}:
        op.add_column("exempted_establishments", sa.Column("ended_on", sa.Date()))


def downgrade():
    if "ended_on" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("exempted_establishments")}:
        op.drop_column("exempted_establishments", "ended_on")
