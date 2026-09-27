"""Contribution filing projections, challans and append-only ledger.

Revision ID: 0002_contribution
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_contribution"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE trrn_sequence START 1")
    op.create_table("establishments", sa.Column("id", sa.String(80), primary_key=True), sa.Column("legal_name", sa.Text, nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("verification_ref", sa.Text))
    op.create_table("establishment_members", sa.Column("uan", sa.String(32), primary_key=True), sa.Column("name", sa.Text, nullable=False), sa.Column("date_of_birth", sa.Date, nullable=False), sa.Column("account_link_id", sa.String(80), nullable=False, unique=True), sa.Column("member_subject", sa.String(80)), sa.Column("establishment_id", sa.String(80), sa.ForeignKey("establishments.id"), nullable=False), sa.Column("date_of_joining", sa.Date), sa.Column("date_of_exit", sa.Date), sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"))
    op.create_table("ecr_filings", sa.Column("id", sa.String(36), primary_key=True), sa.Column("establishment_id", sa.String(80), sa.ForeignKey("establishments.id"), nullable=False), sa.Column("wage_month", sa.String(7), nullable=False), sa.Column("filing_type", sa.String(20), nullable=False), sa.Column("format", sa.String(20), nullable=False), sa.Column("content", sa.Text, nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("state", sa.String(30), nullable=False), sa.Column("preparer_subject", sa.String(80), nullable=False), sa.Column("approver_subject", sa.String(80)), sa.Column("rule_version", sa.String(80), nullable=False), sa.Column("validation_report", sa.JSON), sa.Column("trrn", sa.String(17), unique=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("establishment_id", "wage_month", "version"))
    op.create_index("ix_ecr_filing_month", "ecr_filings", ["establishment_id", "wage_month", "state"])
    op.create_table("challans", sa.Column("trrn", sa.String(17), primary_key=True), sa.Column("filing_id", sa.String(36), sa.ForeignKey("ecr_filings.id"), nullable=False, unique=True), sa.Column("establishment_id", sa.String(80), sa.ForeignKey("establishments.id"), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("total_paise", sa.BigInteger, nullable=False), sa.Column("breakdown", sa.JSON, nullable=False), sa.Column("payment_id", sa.String(80), unique=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("paid_at", sa.DateTime(timezone=True)))
    op.create_table("demo_calculations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("epf_wages_paise", sa.BigInteger, nullable=False), sa.Column("eps_wages_paise", sa.BigInteger, nullable=False), sa.Column("age_years", sa.Integer, nullable=False), sa.Column("rule_version", sa.String(80), nullable=False), sa.Column("result", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("journals", sa.Column("id", sa.String(36), primary_key=True), sa.Column("business_key", sa.String(120), nullable=False, unique=True), sa.Column("kind", sa.String(40), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("reverses_journal_id", sa.String(36), sa.ForeignKey("journals.id")), sa.Column("filing_id", sa.String(36), sa.ForeignKey("ecr_filings.id"), nullable=False))
    op.create_table("journal_lines", sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True), sa.Column("journal_id", sa.String(36), sa.ForeignKey("journals.id"), nullable=False), sa.Column("account_code", sa.String(40), nullable=False), sa.Column("side", sa.String(6), nullable=False), sa.Column("amount_paise", sa.BigInteger, sa.CheckConstraint("amount_paise > 0"), nullable=False), sa.Column("account_link_id", sa.String(80)), sa.Column("share", sa.String(20)))
    op.execute("""CREATE FUNCTION check_journal_balance() RETURNS trigger AS $$
      DECLARE jid text; deb bigint; cred bigint;
      BEGIN jid := COALESCE(NEW.journal_id, OLD.journal_id);
        SELECT COALESCE(sum(amount_paise) FILTER (WHERE side='debit'),0), COALESCE(sum(amount_paise) FILTER (WHERE side='credit'),0)
        INTO deb,cred FROM journal_lines WHERE journal_id=jid;
        IF deb <> cred THEN RAISE EXCEPTION 'unbalanced journal %: debits %, credits %', jid, deb, cred; END IF;
        RETURN NULL;
      END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE CONSTRAINT TRIGGER journal_balance AFTER INSERT OR UPDATE OR DELETE ON journal_lines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_journal_balance()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS journal_balance ON journal_lines")
    op.execute("DROP FUNCTION IF EXISTS check_journal_balance()")
    for table in ("journal_lines", "journals", "demo_calculations", "challans", "ecr_filings", "establishment_members", "establishments"):
        op.drop_table(table)
    op.execute("DROP SEQUENCE IF EXISTS trrn_sequence")
