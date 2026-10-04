"""P2.23b: a rejected claim keeps the rule set's rejection reason, so the member is shown what fixes it."""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    # a fresh database already has the column (an earlier migration builds the table from the current definitions)
    if "decision_reason_code" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("claims")}:
        op.add_column("claims", sa.Column("decision_reason_code", sa.String(40)))


def downgrade():
    op.drop_column("claims", "decision_reason_code")
