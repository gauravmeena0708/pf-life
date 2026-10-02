"""Project exemption end and past accumulation due dates."""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("exempted_establishments")}
    if "ended_on" not in columns:
        op.add_column("exempted_establishments", sa.Column("ended_on", sa.Date()))
    if "past_accumulations_due" not in columns:
        op.add_column("exempted_establishments", sa.Column("past_accumulations_due", sa.Date()))


def downgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("exempted_establishments")}
    for name in ("past_accumulations_due", "ended_on"):
        if name in columns:
            op.drop_column("exempted_establishments", name)
