"""Tables owned by member-service (created by migration 0002)."""
from sqlalchemy import JSON, BigInteger, Column, Date, DateTime, ForeignKey, Integer, MetaData, String, Table, func

metadata = MetaData()
IdType = BigInteger().with_variant(Integer, "sqlite")

members = Table(
    "members", metadata,
    Column("member_id", String(40), primary_key=True),
    Column("uan", String(12), nullable=False, unique=True),
    Column("subject", String(80), unique=True),
    Column("name", String(200), nullable=False),
    Column("date_of_birth", Date, nullable=False),
    Column("gender", String(20), nullable=False),
    Column("mobile_masked", String(40), nullable=False),
    Column("email_masked", String(200), nullable=False),
    Column("bank_ifsc", String(20), nullable=False),
    Column("bank_account_last4", String(4), nullable=False),
    Column("kyc", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

employments = Table(
    "employments", metadata,
    Column("account_link_id", String(40), primary_key=True),
    Column("member_id", String(40), ForeignKey("members.member_id"), nullable=False),
    Column("establishment_id", String(40), nullable=False),
    Column("establishment_name", String(200), nullable=False),
    Column("date_of_joining", Date, nullable=False),
    Column("date_of_exit", Date),
)

notifications = Table(
    "notifications", metadata,
    Column("id", IdType, primary_key=True, autoincrement=True),
    Column("event_id", String(36), nullable=False, unique=True),
    Column("recipient_subject", String(80), nullable=False, index=True),
    Column("template", String(80), nullable=False),
    Column("reference_id", String(80), nullable=False),
    Column("title", String(200), nullable=False),
    Column("body", String(1000), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("read_at", DateTime(timezone=True)),
)
