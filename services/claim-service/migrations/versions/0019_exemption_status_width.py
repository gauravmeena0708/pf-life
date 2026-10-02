"""The exemption status copy holds UNEXEMPTED_COMPLIANCE (21 characters): widen it to 30 (P2.14 fix)."""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("exempted_establishments", "status", type_=sa.String(30), existing_type=sa.String(20), existing_nullable=False)


def downgrade():
    op.alter_column("exempted_establishments", "status", type_=sa.String(20), existing_type=sa.String(30), existing_nullable=False)
