"""Annual interest crediting under the policy rate, a revised rate crediting only the difference, and the TDS
journal. Synthetic balances are brought forward on 2025-03-31, so for 2025-26 interest = balance x rate."""
import copy
from datetime import UTC, datetime

from tests.test_ecr_api import SEED, _deliver, ctx, hdr  # noqa: F401  (ctx is a fixture)

FINANCE = SEED["keycloak_subjects"]["ho-finance"]
MEMBER_B = SEED["members"][1]
URL = "/api/v1/office/accounts/interest-postings"


def finance(step_up=None):
    return hdr(FINANCE, "ho.fa_cao", [], step_up, establishment=None)


def plan(client, fy="2025-26"):
    return client.get(f"{URL}?financialYear={fy}", headers=finance()).json()["data"]


def run(client, fy, total):
    return client.post(URL, json={"financial_year": fy},
                       headers=finance({"action": "post-interest", "resource_id": fy, "amount_paise": abs(total)}))


def publish_rate(rate_bp, name):
    from epfo_persistence.policy import baseline, on_policy_published
    doc = copy.deepcopy(baseline())
    doc["interest"]["rates_bp"]["2025-26"] = rate_bp
    today = datetime.now(UTC).date().isoformat()
    doc.update(rule_version=name, effective_from=today)
    _deliver(on_policy_published, {"version_id": name, "rule_version": name, "effective_from": today, "document_sha256": "x" * 64,
                                   "approved_by_role": "ho.cpfc", "document": doc}, "PolicyPublished.v1")


def test_interest_is_credited_at_the_policy_rate_and_a_revision_credits_only_the_difference(ctx):
    client, q = ctx
    p = plan(client)
    assert p["rate_bp"] == 825 and p["year_ended"] is True
    b = next(a for a in p["accounts"] if a["account_link_id"] == "AL-0002")
    assert (b["employee"]["due_paise"], b["employer"]["due_paise"]) == (247500, 165000)   # ₹30,000 and ₹20,000 at 8.25%
    assert client.post(URL, json={"financial_year": "2025-26"}, headers=finance()).status_code == 428
    assert run(client, "2025-26", p["total_to_credit_paise"] + 100).status_code == 403    # confirmed a different total
    r = run(client, "2025-26", p["total_to_credit_paise"])
    assert r.status_code == 200 and r.json()["data"]["revision"] is False, r.json()
    assert run(client, "2025-26", 0).json()["type"] == "/problems/nothing-to-credit"

    publish_rate(850, "demo-rules-2026.9")                   # the rate for 2025-26 is revised to 8.50%
    p = plan(client)
    b = next(a for a in p["accounts"] if a["account_link_id"] == "AL-0002")
    assert p["rate_bp"] == 850 and (b["employee"]["now_paise"], b["employer"]["now_paise"]) == (7500, 5000)
    r = run(client, "2025-26", p["total_to_credit_paise"])
    assert r.status_code == 200 and r.json()["data"]["revision"] is True
    kinds = [k for (k,) in q("SELECT j.kind FROM journals j JOIN interest_postings i ON i.journal_id=j.id "
                             "WHERE i.account_link_id='AL-0002' ORDER BY i.revision")]
    assert kinds == ["INTEREST", "INTEREST_REVISION"]
    for debit, credit in q("SELECT SUM(CASE WHEN side='debit' THEN amount_paise ELSE 0 END), "
                           "SUM(CASE WHEN side='credit' THEN amount_paise ELSE 0 END) FROM journal_lines GROUP BY journal_id"):
        assert debit == credit
    entries = client.get("/api/v1/members/me/passbook", headers=hdr(MEMBER_B["subject"], "member", [], establishment=None)).json()["data"]["accounts"][0]["entries"]
    assert [(e["kind"], e["description"]) for e in entries][:3] == [
        ("OPENING_BALANCE", "Balance brought forward"), ("INTEREST", "Interest for 2025-26 at 8.25%"),
        ("INTEREST", "Interest for 2025-26 revised to 8.5%: difference")]
    assert entries[2]["running_balance_paise"] == 5000000 + 425000                         # ₹50,000 + ₹4,250 at 8.50%
    history = plan(client)["history"]
    assert [(h["rate_bp"], h["revision"]) for h in history] == [(825, 0), (850, 1)]
    templates = [t for (t,) in q("SELECT event_type FROM outbox")]
    assert templates.count("InterestCredited.v1") == 2


def test_open_year_and_undeclared_rate_are_refused(ctx):
    client, _ = ctx
    assert run(client, "2026-27", 0).json()["type"] == "/problems/financial-year-open"
    assert run(client, "2024-25", 0).json()["type"] == "/problems/interest-rate-not-declared"
    assert client.get(URL, headers=hdr("x", "member", [], establishment=None)).status_code == 403


def test_tds_withheld_is_owed_to_the_tax_department(ctx):
    _, q = ctx
    from app.infra.claims_ledger import on_tax_deducted
    payload = {"claim_id": "CLM-T", "account_link_id": "AL-0006", "gross_paise": 6000000, "tds_paise": 600000, "net_paise": 5400000,
               "rate_bp": 1000, "rule_version": "demo-rules-2026.1", "basis": "10% with a verified PAN."}
    _deliver(on_tax_deducted, payload, "TaxDeducted.v1")
    _deliver(on_tax_deducted, payload, "TaxDeducted.v1")
    assert q("SELECT account_code, side, amount_paise FROM journal_lines jl JOIN journals j ON j.id=jl.journal_id "
             "WHERE j.business_key='TDS-CLM-T' ORDER BY account_code") == [("CLAIMS_PAYABLE", "debit", 600000), ("TDS_PAYABLE", "credit", 600000)]
