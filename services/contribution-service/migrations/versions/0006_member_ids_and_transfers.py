"""One row per member ID (a UAN can have several), and Form 13 transfer postings.

Revision ID: 0006
"""
import sqlalchemy as sa
from alembic import op

from app.infra.models import TransferPosting

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    pk = sa.inspect(bind).get_pk_constraint("establishment_members")
    if pk.get("constrained_columns") == ["uan"]:            # 0002 builds from the current definitions on a fresh database
        op.drop_constraint(pk["name"], "establishment_members", type_="primary")
        op.create_primary_key("establishment_members_pkey", "establishment_members", ["account_link_id"])
        op.create_index("ix_establishment_members_uan", "establishment_members", ["uan"])
    TransferPosting.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    TransferPosting.__table__.drop(bind=op.get_bind(), checkfirst=True)
