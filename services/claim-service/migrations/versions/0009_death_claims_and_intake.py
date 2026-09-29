"""Death and EDLI claims (nominations, beneficiaries and shares) and physical intake at the PRO counter.

Revision ID: 0009
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import claim_beneficiaries, nominations, physical_intakes

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "deceased_on" not in {c["name"] for c in sa.inspect(bind).get_columns("accounts")}:     # 0002 builds from the current definitions
        op.add_column("accounts", sa.Column("deceased_on", sa.Date))
    if "death_of_uan" not in {c["name"] for c in sa.inspect(bind).get_columns("claims")}:
        op.add_column("claims", sa.Column("death_of_uan", sa.String(12)))
    for table in (nominations, claim_beneficiaries, physical_intakes):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    for table in (physical_intakes, claim_beneficiaries, nominations):
        table.drop(bind=op.get_bind(), checkfirst=True)
    op.drop_column("claims", "death_of_uan")
    op.drop_column("accounts", "deceased_on")
