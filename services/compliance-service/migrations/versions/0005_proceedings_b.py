"""Section, parent case, covered demands and the order on inquiries (P2.11b: 7B, 7C, 14B / 7Q, set-aside).

Revision ID: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

COLUMNS = [sa.Column("section", sa.String(4), nullable=False, server_default="7A"), sa.Column("parent_case_id", sa.String(40)),
           sa.Column("demand_ids", sa.JSON()), sa.Column("ordered_at", sa.DateTime(timezone=True)), sa.Column("ex_parte", sa.Boolean()),
           sa.Column("order_demand_ids", sa.JSON())]


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("inquiries")}
    for column in COLUMNS:
        if column.name not in have:
            op.add_column("inquiries", column)


def downgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("inquiries")}
    for column in reversed(COLUMNS):
        if column.name in have:
            op.drop_column("inquiries", column.name)
