"""P2.19: contribution-service consumes UanMerged.v1, moves PF balance with balanced journal,
reflects in active UAN passbook, attaches continuous service history, and redelivery is idempotent."""
import asyncio
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select, text

from tests.test_ecr_api import SEED, _deliver, ctx, hdr  # noqa: F401
from tests.test_inoperative import sql

ACTIVE = SEED["members"][0]
ACTIVE_UAN = ACTIVE["uan"]
ACTIVE_LINK = ACTIVE["account_link_id"]
ACTIVE_SUB = ACTIVE["subject"]

DUPLICATE_UAN = "199999999992"
DUP_LINK = "AL-DUP-0002"


def seed_duplicate_with_balance(emp_paise=30000, er_paise=20000):
    # Insert establishment_member for duplicate
    sql(f"""
        INSERT INTO establishment_members (uan, name, date_of_birth, account_link_id, member_subject,
                                          establishment_id, date_of_joining, date_of_exit, status, international_worker)
        VALUES ('{DUPLICATE_UAN}', 'KIRAN VERMA', '1990-05-15', '{DUP_LINK}', 'dup-subject-002',
                'EST-DEMO-0001', '2023-01-01', '2024-12-31', 'EXITED', 0)
        ON CONFLICT (account_link_id) DO UPDATE SET uan=excluded.uan
    """)

    # Seed opening balance for DUP_LINK if positive
    total = emp_paise + er_paise
    if total > 0:
        jid = str(uuid.uuid4())
        key = f"OPENING-{DUP_LINK}"
        sql(f"""
            INSERT INTO journals (id, business_key, kind, occurred_at, filing_id, claim_id)
            VALUES ('{jid}', '{key}', 'OPENING_BALANCE', CURRENT_TIMESTAMP, NULL, NULL)
        """)
        sql(f"INSERT INTO journal_lines (journal_id, account_code, side, amount_paise, account_link_id, share) VALUES ('{jid}', 'OPENING_BALANCE_BF', 'debit', {total}, NULL, NULL)")
        sql(f"INSERT INTO journal_lines (journal_id, account_code, side, amount_paise, account_link_id, share) VALUES ('{jid}', 'AC01_EPF', 'credit', {emp_paise}, '{DUP_LINK}', 'employee')")
        sql(f"INSERT INTO journal_lines (journal_id, account_code, side, amount_paise, account_link_id, share) VALUES ('{jid}', 'AC01_EPF', 'credit', {er_paise}, '{DUP_LINK}', 'employer')")


def test_uan_merged_moves_balance_balanced_journal_and_passbook(ctx):
    client, q = ctx
    seed_duplicate_with_balance(emp_paise=30000, er_paise=20000)

    from app.infra.transfers import on_uan_merged
    payload = {
        "active_uan": ACTIVE_UAN,
        "duplicate_uan": DUPLICATE_UAN,
        "account_link_ids": [DUP_LINK],
        "merged_at": datetime.now(UTC).isoformat()
    }

    # Deliver UanMerged.v1
    applied, event = _deliver(on_uan_merged, payload, "UanMerged.v1")
    assert applied is True

    # 1. Balanced journal posted with business key UANMERGE-<duplicate_uan>-<account_link_id>
    bkey = f"UANMERGE-{DUPLICATE_UAN}-{DUP_LINK}"
    journal_rows = q(f"SELECT id, kind FROM journals WHERE business_key='{bkey}'")
    assert len(journal_rows) == 1
    jid = journal_rows[0][0]

    lines = q(f"SELECT account_code, side, amount_paise, account_link_id, share FROM journal_lines WHERE journal_id='{jid}'")
    assert len(lines) == 4
    debits = sum(r[2] for r in lines if r[1] == "debit")
    credits = sum(r[2] for r in lines if r[1] == "credit")
    assert debits == 50000 and credits == 50000  # Balanced journal

    # Debits on duplicate, credits on active
    assert sorted([(r[1], r[2], r[3], r[4]) for r in lines]) == sorted([
        ("debit", 30000, DUP_LINK, "employee"),
        ("debit", 20000, DUP_LINK, "employer"),
        ("credit", 30000, ACTIVE_LINK, "employee"),
        ("credit", 20000, ACTIVE_LINK, "employer"),
    ])

    # 2. Service history continuous: duplicate account link attached to active UAN
    owner_uan = q(f"SELECT uan FROM establishment_members WHERE account_link_id='{DUP_LINK}'")[0][0]
    assert owner_uan == ACTIVE_UAN

    # 3. Passbook of active UAN shows the transferred balance
    book = client.get("/api/v1/members/me/passbook", headers=hdr(ACTIVE_SUB, "member", [], establishment=None)).json()["data"]
    accounts_by_id = {a["account_link_id"]: a for a in book["accounts"]}

    # Active account link received the transfer
    assert ACTIVE_LINK in accounts_by_id
    active_entries = accounts_by_id[ACTIVE_LINK]["entries"]
    assert any(e["kind"] == "TRANSFER_IN" and (e["employee_share_paise"] + e["employer_share_paise"] == 50000) for e in active_entries)

    # Duplicate account link is transferred out with 0 final balance
    assert DUP_LINK in accounts_by_id
    dup_entries = accounts_by_id[DUP_LINK]["entries"]
    assert dup_entries[-1]["running_balance_paise"] == 0
    assert any(e["kind"] == "TRANSFER_OUT" for e in dup_entries)

    # 4. Redelivery is idempotent
    import app.infra.db as db
    from epfo_persistence.consumer import apply_once
    # Consumer-level inbox deduplication
    assert asyncio.run(apply_once(db.sessions(), event, on_uan_merged)) is False

    # Handler-level business key idempotency check
    async def run_again():
        async with db.sessions()() as s:
            await on_uan_merged(s, event)
    asyncio.run(run_again())

    # Still exactly one journal
    assert q(f"SELECT COUNT(*) FROM journals WHERE business_key='{bkey}'")[0][0] == 1


def test_uan_merged_zero_balance_moves_nothing_but_is_recorded(ctx):
    client, q = ctx
    zero_dup_uan = "199999999993"
    zero_dup_link = "AL-DUP-0003"

    sql(f"""
        INSERT INTO establishment_members (uan, name, date_of_birth, account_link_id, member_subject,
                                          establishment_id, date_of_joining, date_of_exit, status, international_worker)
        VALUES ('{zero_dup_uan}', 'ZERO BALANCE', '1992-01-01', '{zero_dup_link}', 'zero-sub',
                'EST-DEMO-0001', '2023-01-01', '2024-12-31', 'EXITED', 0)
        ON CONFLICT (account_link_id) DO UPDATE SET uan=excluded.uan
    """)

    from app.infra.transfers import on_uan_merged
    payload = {
        "active_uan": ACTIVE_UAN,
        "duplicate_uan": zero_dup_uan,
        "account_link_ids": [zero_dup_link],
        "merged_at": datetime.now(UTC).isoformat()
    }

    applied, event = _deliver(on_uan_merged, payload, "UanMerged.v1")
    assert applied is True

    bkey = f"UANMERGE-{zero_dup_uan}-{zero_dup_link}"
    journal_rows = q(f"SELECT id, kind FROM journals WHERE business_key='{bkey}'")
    assert len(journal_rows) == 1
    jid = journal_rows[0][0]

    # Zero balance moves nothing (0 journal lines)
    lines = q(f"SELECT COUNT(*) FROM journal_lines WHERE journal_id='{jid}'")
    assert lines[0][0] == 0

    # Service periods attached to active UAN
    owner_uan = q(f"SELECT uan FROM establishment_members WHERE account_link_id='{zero_dup_link}'")[0][0]
    assert owner_uan == ACTIVE_UAN
