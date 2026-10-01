"""Record EPS service transfers and the PF exemption snapshot for estimates."""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import eps_transfers, exempted_establishments

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "transferred_to" not in {c["name"] for c in sa.inspect(bind).get_columns("eps_accounts")}:
        op.add_column("eps_accounts", sa.Column("transferred_to", sa.String(40)))
    eps_transfers.create(bind, checkfirst=True)
    exempted_establishments.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    exempted_establishments.drop(bind, checkfirst=True)
    eps_transfers.drop(bind, checkfirst=True)
    if "transferred_to" in {c["name"] for c in sa.inspect(bind).get_columns("eps_accounts")}:
        op.drop_column("eps_accounts", "transferred_to")
