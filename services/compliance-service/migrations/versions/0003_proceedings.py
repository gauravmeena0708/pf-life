"""Inspections and section 7A proceedings.

Revision ID: 0003
"""
from alembic import op
from app.infra.tables import compliance_officers, inspections, inspection_steps, inquiries, inquiry_actions

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in (compliance_officers, inspections, inspection_steps, inquiries, inquiry_actions):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (inquiry_actions, inquiries, inspection_steps, inspections, compliance_officers):
        table.drop(bind=bind, checkfirst=True)
