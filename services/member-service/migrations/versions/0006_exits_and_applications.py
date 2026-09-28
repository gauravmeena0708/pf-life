"""Member-marked and employer-approved exits, last contribution month, transfers, and the member's applications.

Revision ID: 0006
"""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import member_applications

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("employments")}
    for name, kind in (("exit_reason", sa.String(40)), ("exit_marked_by", sa.String(20)),
                       ("last_contribution_month", sa.String(7)), ("transferred_to", sa.String(40))):
        if name not in columns:                    # 0002 builds from the current definitions on a fresh database
            op.add_column("employments", sa.Column(name, kind))
    member_applications.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    member_applications.drop(bind=op.get_bind(), checkfirst=True)
    for name in ("transferred_to", "last_contribution_month", "exit_marked_by", "exit_reason"):
        op.drop_column("employments", name)
