"""Notification preferences and delivery evidence."""
import sqlalchemy as sa
from alembic import op

from app.infra.tables import notification_preferences, notification_deliveries, notification_delivery_attempts

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in (notification_preferences, notification_deliveries, notification_delivery_attempts):
        if not sa.inspect(bind).has_table(table.name):
            table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (notification_delivery_attempts, notification_deliveries, notification_preferences):
        if sa.inspect(bind).has_table(table.name):
            table.drop(bind, checkfirst=True)
