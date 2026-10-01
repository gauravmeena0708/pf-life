"""Higher pension dues move from the member PF ledger to EPS once per option."""
import json

from tests.test_ecr_api import SEED, _deliver, ctx, hdr  # noqa: F401


def _events(q, kind):
    return [json.loads(raw)["envelope"]["payload"] for (raw,) in
            q(f"SELECT payload FROM outbox WHERE event_type='{kind}' ORDER BY id")]


def _request(option_id, amount):
    member = SEED["members"][0]
    return {"option_id": option_id, "uan": member["uan"],
            "account_link_id": member["account_link_id"], "amount_paise": amount}


def test_transfer_posts_balanced_employer_first_and_only_once(ctx):
    client, q = ctx
    from app.infra.messaging import BINDINGS, dispatch

    assert "pension-service.HigherPensionDuesTransferRequested.v1" in BINDINGS
    request = _request("HPO-1", 300000000)
    assert _deliver(dispatch, request, "HigherPensionDuesTransferRequested.v1")[0]
    [(journal_id, kind)] = q("SELECT id, kind FROM journals WHERE business_key='HP-HPO-1'")
    assert kind == "HIGHER_PENSION_TRANSFER"
    lines = q(f"SELECT account_code, side, share, amount_paise FROM journal_lines WHERE journal_id='{journal_id}' ORDER BY id")
    assert lines == [("AC01_EPF", "debit", "employer", 240000000),
                     ("AC01_EPF", "debit", "employee", 60000000),
                     ("AC10_EPS", "credit", None, 300000000)]
    assert sum(line[3] for line in lines if line[1] == "debit") == sum(line[3] for line in lines if line[1] == "credit")
    assert _events(q, "HigherPensionTransferPosted.v1") == [
        {"option_id": "HPO-1", "status": "POSTED", "posted_paise": 300000000, "journal_id": journal_id}]
    adjusted = _events(q, "LedgerAdjusted.v1")
    assert len(adjusted) == 1
    assert adjusted[0] == {"adjustment_id": "HPO-1", "journal_id": journal_id,
                           "account_link_id": request["account_link_id"], "appendix_type": "EPS_DIVERSION",
                           "postings": [{"account_code": code, "side": side, "amount_paise": amount,
                                         **({"account_link_id": request["account_link_id"], "share": share} if share else {})}
                                        for code, side, share, amount in lines]}
    _deliver(dispatch, request, "HigherPensionDuesTransferRequested.v1")  # a new event ID for the same option
    assert q("SELECT count(*) FROM journals WHERE business_key='HP-HPO-1'")[0][0] == 1
    assert len(_events(q, "HigherPensionTransferPosted.v1")) == 1
    assert len(_events(q, "LedgerAdjusted.v1")) == 1

    member = SEED["members"][0]
    book = client.get("/api/v1/members/me/passbook",
                      headers=hdr(member["subject"], "member", [], establishment=None)).json()["data"]
    entry = next(e for e in book["accounts"][0]["entries"] if e["kind"] == "HIGHER_PENSION_TRANSFER")
    assert entry["description"] == "Higher pension dues transferred from PF to pension fund"
    assert (entry["employee_share_paise"], entry["employer_share_paise"], entry["running_balance_paise"]) == (
        -60000000, -240000000, 300000000)


def test_insufficient_balance_posts_no_journal(ctx):
    _, q = ctx
    from app.infra.messaging import dispatch

    _deliver(dispatch, _request("HPO-2", 600000001), "HigherPensionDuesTransferRequested.v1")
    assert q("SELECT id FROM journals WHERE business_key='HP-HPO-2'") == []
    assert _events(q, "HigherPensionTransferPosted.v1") == [
        {"option_id": "HPO-2", "status": "INSUFFICIENT_BALANCE", "posted_paise": 0, "journal_id": None}]
    assert _events(q, "LedgerAdjusted.v1") == []
