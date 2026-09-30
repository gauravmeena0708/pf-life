"""The NDC Issue Tracker (Phase 2, slice 8e).

Revision ID: 0003
"""
from alembic import op

from app.infra.tables import issue_tracker_requests

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    issue_tracker_requests.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("issue_tracker_requests")
