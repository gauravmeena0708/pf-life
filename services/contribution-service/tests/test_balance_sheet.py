"""Head-office balance sheet from the posted ledger."""
from datetime import date

from tests.test_ecr_api import SEED, _deliver, ctx, hdr  # noqa: F401
from tests.test_returns import regular_posted

URL = "/api/v1/ho/finance/balance-sheet"


def auth(role="ho.fa_cao"):
    return hdr("finance-reader", role, [], establishment=None)


def sheet(client, as_of=None):
    response = client.get(URL, params={"as_of": as_of} if as_of else None, headers=auth())
    assert response.status_code == 200, response.json()
    return response.json()["data"]


def line(data, side, code):
    return next((item["amount_paise"] for item in data[side] if item["code"] == code), 0)


def test_seed_is_balanced_and_read_is_audited(ctx):
    client, q = ctx
    data = sheet(client)
    assert data["balanced"] is True
    assert data["total_assets_paise"] == data["total_liabilities_paise"] > 0
    assert data["journals_counted"] == len(q("SELECT id FROM journals"))
    assert line(data, "assets", "OPENING_BALANCE_BF") == line(data, "liabilities", "AC01_EPF")
    assert data["as_of"] == date.today().isoformat()
    assert q("SELECT action, target_id FROM audit_local WHERE action='finance.balance_sheet'") == [
        ("finance.balance_sheet", data["as_of"])]


def test_contribution_and_claim_move_their_ledger_lines(ctx):
    client, _ = ctx
    before = sheet(client)
    regular_posted(client)
    posted = sheet(client)
    increase = line(posted, "assets", "BANK_COLLECTION") - line(before, "assets", "BANK_COLLECTION")
    assert increase > 0
    assert line(posted, "liabilities", "AC01_EPF") > line(before, "liabilities", "AC01_EPF")
    assert posted["balanced"] is True

    from app.infra.claims_ledger import on_claim_decision
    _deliver(on_claim_decision, {"claim_id": "CLM-BS", "decision": "APPROVED", "reason_code": "OFFICER_APPROVED",
                                 "rule_version": "r", "amount_paise": 100000, "account_link_id": SEED["members"][0]["account_link_id"]},
             "ClaimDecisionRecorded.v1")
    claimed = sheet(client)
    assert line(claimed, "liabilities", "AC01_EPF") == line(posted, "liabilities", "AC01_EPF") - 100000
    assert line(claimed, "liabilities", "CLAIMS_PAYABLE") == 100000
    assert claimed["balanced"] is True
    assert claimed["journals_counted"] == posted["journals_counted"] + 1


def test_as_of_excludes_later_journals(ctx):
    client, q = ctx
    seed = sheet(client, "2026-08-31")
    regular_posted(client)
    earlier = sheet(client, "2026-08-31")
    assert earlier["total_assets_paise"] == seed["total_assets_paise"]
    assert earlier["journals_counted"] == seed["journals_counted"]
    assert sheet(client)["journals_counted"] > earlier["journals_counted"]


def test_roles_and_bad_date(ctx):
    client, _ = ctx
    assert client.get(URL, headers=auth("gov.statutory_auditor")).status_code == 200
    assert client.get(URL, headers=auth("member")).status_code == 403
    assert client.get(URL, params={"as_of": "2026-13-99"}, headers=auth()).status_code == 422
