"""P2.19: Edge cases - attachment orders (EPF Act s.10), bank merger IFSC successors,
shared bank accounts, minor nominees and para 70 death distributions.
"""
import sqlalchemy as sa
from alembic import op
from app.infra.tables import attachment_orders, bank_ifsc_successors

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Attachment orders table
    attachment_orders.create(bind=bind, checkfirst=True)

    # 2. Bank IFSC successors table
    bank_ifsc_successors.create(bind=bind, checkfirst=True)

    # 3. Claims ifsc_remapped
    claim_cols = {c["name"] for c in inspector.get_columns("claims")}
    if "ifsc_remapped" not in claim_cols:
        op.add_column("claims", sa.Column("ifsc_remapped", sa.Boolean(), server_default=sa.false(), nullable=False))

    # 4. Nominations minor and guardian_name
    nom_cols = {c["name"] for c in inspector.get_columns("nominations")}
    if "minor" not in nom_cols:
        op.add_column("nominations", sa.Column("minor", sa.Boolean(), server_default=sa.false(), nullable=False))
    if "guardian_name" not in nom_cols:
        op.add_column("nominations", sa.Column("guardian_name", sa.String(120)))

    # 5. Claim beneficiaries minor, guardian_name, guardian_account_last4
    ben_cols = {c["name"] for c in inspector.get_columns("claim_beneficiaries")}
    if "minor" not in ben_cols:
        op.add_column("claim_beneficiaries", sa.Column("minor", sa.Boolean(), server_default=sa.false(), nullable=False))
    if "guardian_name" not in ben_cols:
        op.add_column("claim_beneficiaries", sa.Column("guardian_name", sa.String(120)))
    if "guardian_account_last4" not in ben_cols:
        op.add_column("claim_beneficiaries", sa.Column("guardian_account_last4", sa.String(4)))


def downgrade():
    op.drop_column("claim_beneficiaries", "guardian_account_last4")
    op.drop_column("claim_beneficiaries", "guardian_name")
    op.drop_column("claim_beneficiaries", "minor")
    op.drop_column("nominations", "guardian_name")
    op.drop_column("nominations", "minor")
    op.drop_column("claims", "ifsc_remapped")
    op.drop_table("bank_ifsc_successors")
    op.drop_table("attachment_orders")
