"""P2.19c: a member ID found not eligible for EPS has its pension service deleted (HO circular WSU/2025/E-961539)."""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    if "eps_member" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("eps_accounts")}:   # fresh: built already
        op.add_column("eps_accounts", sa.Column("eps_member", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("eps_accounts", "eps_member")
