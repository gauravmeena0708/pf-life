"""Illustrative tax documents use only paid claims and their fixed TDS snapshots."""
import asyncio
from datetime import UTC, datetime

from sqlalchemy import text

from epfo_persistence.policy import financial_year
from tests.test_claims_api import SUBJECTS, ctx, events, hdr, member  # noqa: F401
from tests.test_tds import AMOUNT, final_settlement, pay

MEMBER_C = SUBJECTS["member-c"]
DA = SUBJECTS["do-caseworker"]
FY = financial_year(datetime.now(UTC).date())
CERT = "/api/v1/members/me/tax/form-16a"
FILE = "/api/v1/office/tds/computations"


def _move_settlement(claim_id, when):
    from app.infra.db import engine

    async def move():
        async with engine().begin() as conn:
            await conn.execute(text("UPDATE claim_timeline SET at = :at WHERE claim_id = :id AND state = 'SETTLED'"),
                               {"at": when, "id": claim_id})
    asyncio.run(move())


def test_certificate_with_and_without_tds(ctx):
    client, _, deliver = ctx
    empty = client.get(CERT, headers=member(MEMBER_C))
    assert empty.status_code == 200, empty.json()
    assert empty.json()["data"]["totals"] == {"amount_paid_paise": 0, "tds_paise": 0}
    assert len(empty.json()["data"]["quarters"]) == 4
    assert "No tax was deducted" in empty.json()["data"]["note"]

    claim_id = final_settlement(client)
    pay(client, deliver, claim_id, "document-tax")
    response = client.get(CERT, headers=member(MEMBER_C))
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["certificate_no"] == f"16A/{FY}/0006/1"
    assert data["deductee"] == {"name": "FARAH DEMO", "pan_masked": None, "pan_status": "VERIFIED"}
    assert data["section"] == "192A" and "not valid for filing" in data["note"]
    assert data["totals"] == {"amount_paid_paise": AMOUNT, "tds_paise": 600000}
    assert [i["claim_id"] for q in data["quarters"] for i in q["items"]] == [claim_id]
    assert data["quarters"][0]["quarter"] == "Q1"


def test_financial_year_validation_and_empty_other_year(ctx):
    client, _, _ = ctx
    assert client.get(CERT, params={"financialYear": "2026-28"}, headers=member(MEMBER_C)).status_code == 422
    assert client.get(CERT, params={"financialYear": "bad"}, headers=member(MEMBER_C)).status_code == 422
    result = client.get(CERT, params={"financialYear": "2020-21"}, headers=member(MEMBER_C))
    assert result.status_code == 200 and result.json()["data"]["totals"]["tds_paise"] == 0


def test_quarterly_filing_totals_repeat_and_authorization(ctx):
    client, q, deliver = ctx
    first = final_settlement(client)
    pay(client, deliver, first, "file-tax-1")
    second = final_settlement(client)
    pay(client, deliver, second, "file-tax-2")
    for claim_id in (first, second):
        _move_settlement(claim_id, "2026-03-31 12:00:00")
    body = {"financial_year": "2025-26", "quarter": "Q4"}
    assert client.post(FILE, json=body, headers=member(MEMBER_C)).status_code == 403
    response = client.post(FILE, json=body, headers=hdr(DA, "fo.da_accounts"))
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["totals"] == {"amount_paid_paise": 2 * AMOUNT, "tds_paise": 1200000}
    assert len(data["deductees"]) == 2
    assert {r["uan_masked"] for r in data["deductees"]} == {"********0006"}
    assert data["acknowledgement"].startswith("26Q-ACK-")
    [event] = events(q, "TdsStatementFiled.v1")
    assert event["filing_id"] == data["filing_id"] and event["tds_paise"] == 1200000
    assert event["acknowledgement"] == data["acknowledgement"]
    assert len(q("SELECT filing_id FROM tds_filings")) == 1
    repeat = client.post(FILE, json=body, headers=hdr(DA, "fo.da_accounts"))
    assert repeat.status_code == 409 and repeat.json()["type"] == "/problems/already-filed"
    assert data["acknowledgement"] in repeat.json()["detail"]
    assert len(events(q, "TdsStatementFiled.v1")) == 1


def test_future_quarter_and_invalid_fy(ctx):
    client, _, _ = ctx
    assert client.post(FILE, json={"financial_year": FY, "quarter": "Q4"},
                       headers=hdr(DA, "fo.da_accounts")).status_code == 422
    assert client.post(FILE, json={"financial_year": "2026-28", "quarter": "Q1"},
                       headers=hdr(DA, "fo.da_accounts")).status_code == 422
