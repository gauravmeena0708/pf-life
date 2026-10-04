"""Order-safe demand copies: the time of the event that set each demand's state, so an older event never wins."""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    if "source_at" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("demands")}:   # fresh: built already
        op.add_column("demands", sa.Column("source_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("demands", "source_at")
