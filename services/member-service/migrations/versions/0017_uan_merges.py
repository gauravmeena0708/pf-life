"""P2.19: merge duplicate UANs into active UAN."""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import uan_merges

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("members")}
    for name, col in (
        ("merged_into", sa.Column("merged_into", sa.String(12))),
        ("merged_at", sa.Column("merged_at", sa.DateTime(timezone=True))),
        ("merged_by", sa.Column("merged_by", sa.String(80))),
    ):
        if name not in cols:
            op.add_column("members", col)
    if not sa.inspect(bind).has_table(uan_merges.name):
        uan_merges.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(uan_merges.name):
        uan_merges.drop(bind, checkfirst=True)
    cols = {c["name"] for c in sa.inspect(bind).get_columns("members")}
    for name in ("merged_by", "merged_at", "merged_into"):
        if name in cols:
            op.drop_column("members", name)
