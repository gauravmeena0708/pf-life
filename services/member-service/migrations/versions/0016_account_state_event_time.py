"""Order-safe member account_state copy: the time of the event that set account_state, so an older event never wins."""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "account_state_updated_at" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("members")}:
        op.add_column("members", sa.Column("account_state_updated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("members", "account_state_updated_at")
