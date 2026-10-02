"""A disabled child's family pension is for life (Pension Manual 2.13.10; P2.19)."""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("family_members", sa.Column("disabled", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("family_members", "disabled")
