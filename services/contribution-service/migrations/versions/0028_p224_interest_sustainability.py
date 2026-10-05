"""P2.24 interest sustainability model: fund_asset_classes and yield_assumptions."""
from alembic import op

from app.infra.models import FundAssetClass, FundPositionSnapshot, YieldAssumption

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    FundAssetClass.__table__.create(bind=bind, checkfirst=True)
    FundPositionSnapshot.__table__.create(bind=bind, checkfirst=True)
    YieldAssumption.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    YieldAssumption.__table__.drop(bind=bind, checkfirst=True)
    FundPositionSnapshot.__table__.drop(bind=bind, checkfirst=True)
    FundAssetClass.__table__.drop(bind=bind, checkfirst=True)
