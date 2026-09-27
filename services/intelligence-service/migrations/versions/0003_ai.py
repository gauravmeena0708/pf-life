"""Journey E: claim facts, grievance links, office postings, AI interaction log and feedback.

Revision ID: 0003
"""
from alembic import op

from app.infra.tables import ai_feedback, ai_interactions, claim_facts, grievance_links, metadata, office_staff

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None
TABLES = [claim_facts, grievance_links, office_staff, ai_interactions, ai_feedback]


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), tables=TABLES)


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind(), tables=TABLES)
