"""Principal employer tagged contribution facts. Revision ID: 0005."""
from alembic import op

from app.infra.tables import principal_employer_tags

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    principal_employer_tags.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    principal_employer_tags.drop(bind=op.get_bind(), checkfirst=True)
