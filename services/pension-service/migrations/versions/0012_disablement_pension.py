"""Disablement pension (EPS para 15; P2.13): the reason a member ID was left, the disablement on a pension claim, and the
kind of a pension in payment (a disablement pension is revised without an age test)."""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _add(table, column):
    if column.name not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}:   # an earlier migration builds
        op.add_column(table, column)                                     # from the current definitions: a fresh database has it


def upgrade():
    _add("eps_accounts", sa.Column("exit_reason", sa.String(40)))
    _add("pension_claims", sa.Column("disablement", sa.JSON))
    _add("pensioners", sa.Column("pension_kind", sa.String(12), nullable=False, server_default="MEMBER"))


def downgrade():
    op.drop_column("pensioners", "pension_kind")
    op.drop_column("pension_claims", "disablement")
    op.drop_column("eps_accounts", "exit_reason")
