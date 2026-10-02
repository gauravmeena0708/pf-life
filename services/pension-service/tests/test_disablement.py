"""P2.13: disablement pension (EPS para 15; Pension Manual 2.5.2.3, 2.7 and Figure 6) — permanently and totally disabled in
service: the formula as if retiring on the day of invalidation, whatever the age or service, from the day after the exit."""
from datetime import date

from tests.test_pensioner_services import at
from tests.test_pensions import SUBJECTS, ctx  # noqa: F401  (ctx is a fixture)
from tests.test_settlement import DA_ACC, DA_P, AO, APFC_P, MEMBER_E, step

SURESH = SUBJECTS["member-disabled"]
URL = "/api/v1/members/me/pension-applications"
CERT = {"date_of_disablement": "2026-08-12", "certificate_kind": "MEDICAL_BOARD", "certificate_ref": "MB/DL/2026/0815",
        "issued_by": "Medical Board, Government Hospital (synthetic)", "permanent_and_total": True}


def test_disabled_after_7_years_gets_a_pension_without_the_age_or_service_test(ctx, monkeypatch):
    client, _, _ = ctx
    at(monkeypatch, date(2026, 9, 29))
    plain = step(client, "POST", URL, SURESH, "member", {})
    assert plain.status_code == 422 and "10 years" in plain.json()["detail"]                    # a monthly pension needs 10 years
    for bad, why in (({**CERT, "date_of_disablement": "2026-08-25"}, "while in service"),
                     ({**CERT, "permanent_and_total": False}, "permanently and totally unfit")):
        r = step(client, "POST", URL, SURESH, "member", {"disablement": bad})
        assert r.status_code == 422 and why in r.json()["detail"], r.json()
    other = step(client, "POST", URL, MEMBER_E, "member", {"disablement": {**CERT, "date_of_disablement": "2026-01-10"}})
    assert "permanent and total disablement" in other.json()["detail"]                       # his exit was not for disablement
    r = step(client, "POST", URL, SURESH, "member", {"disablement": CERT})
    assert r.status_code == 201, r.json()
    c = r.json()["data"]
    assert (c["kind"], c["pension_from"], c["service_months"]) == ("DISABLED", "2026-08-21", 88)
    assert c["estimate"]["monthly_paise"] == 150000 and c["estimate"]["working"].startswith("Disablement pension")   # ₹15,000 x 7 / 70
    assert c["disablement"]["certificate_ref"] == "MB/DL/2026/0815"
    cid = c["claim_id"]
    c = step(client, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets", DA_ACC, "fo.da_accounts",
             {"service_months": 88, "pensionable_salary_paise": 1500000, "note": "Service and wages checked with the ledger"}).json()["data"]
    ids = c["ids"]["ids_id"]
    step(client, "POST", f"/api/v1/office/pension-claims/{cid}/input-data-sheets/{ids}/approvals", AO, "fo.ao",
         {"decision": "APPROVE", "note": "IDS in order"}, "approve-ids", ids)
    ws = step(client, "POST", "/api/v1/office/pensions/worksheets", DA_P, "fo.da_pension", {"claim_id": cid}).json()["data"]["worksheet"]
    assert ws["monthly_paise"] == 150000 and ws["age_at_start"] == 46                           # no reduction at 46
    step(client, "POST", f"/api/v1/office/pensions/worksheets/{ws['worksheet_id']}/approvals", APFC_P, "fo.apfc_pension",
         {"decision": "APPROVE", "note": "Medical certificate scrutinised"}, "approve-worksheet", ws["worksheet_id"])
    ppo = step(client, "POST", "/api/v1/office/pensions/ppo-issuances", DA_P, "fo.da_pension", {"claim_id": cid}, "issue-ppo", cid).json()["data"]["ppo_id"]
    _, q, _ = ctx
    assert q(f"SELECT pension_kind, age_at_start, subject FROM pensioners WHERE ppo_id='{ppo}'") == [("DISABLED", 46, None)]


def test_the_formula_for_disablement():
    from epfo_persistence.policy import baseline, pension_on
    rules = baseline()
    one_month = pension_on(1500000, 1, 30, rules, disablement=True)
    assert one_month["eligible"] and one_month["monthly_paise"] == rules["pension"]["minimum_pension_paise"]   # raised to the minimum
    assert not pension_on(1500000, 0, 30, rules, disablement=True)["eligible"]                 # not a month's contribution
    assert not pension_on(1500000, 88, 46, rules)["eligible"]                                   # the ordinary pension: 10 years


def test_a_childs_family_pension_ends_at_25_unless_the_child_is_disabled(ctx):
    """P2.19 (Pension Manual 2.10.5, 2.13.10): months after the 25th birthday are not paid and the pension ceases; a disabled
    child's pension goes on for life."""
    import asyncio
    from app.domain.pension import catch_up_payments
    from app.infra.db import sessions
    from app.infra.tables import pension_payments, pensioners
    from sqlalchemy import insert, select
    _, q, _ = ctx
    base = {"subject": None, "uan": "100000000999", "service_months": 120, "pensionable_salary_paise": 1500000, "age_at_start": 20,
            "office_id": "RO-DEMO-01", "bank_ifsc": "DEMO0000000", "bank_account_last4": "0000", "original_monthly_paise": 75000,
            "original_rule_version": "demo-rules-2026.1", "original_working": "child", "status": "IN_PAYMENT", "pension_start": date(2025, 1, 1),
            "date_of_birth": date(2001, 3, 15)}

    async def run():
        async with sessions()() as s, s.begin():
            for ppo, kind in (("PPO-CHILD-1", "CHILD"), ("PPO-CHILD-2", "DIS_CHILD")):
                await s.execute(insert(pensioners).values(ppo_id=ppo, name=ppo, pension_kind=kind, **base))
                row = dict((await s.execute(select(pensioners).where(pensioners.c.ppo_id == ppo))).mappings().one())
                await catch_up_payments(s, row, on=date(2026, 9, 30))
    asyncio.run(run())
    paid = dict(q("SELECT ppo_id, COUNT(*) FROM pension_payments WHERE ppo_id LIKE 'PPO-CHILD-%' GROUP BY ppo_id"))
    assert paid == {"PPO-CHILD-1": 15, "PPO-CHILD-2": 20}                     # Jan 2025 – Mar 2026 (25 in March 2026); to Aug 2026
    assert q("SELECT status FROM pensioners WHERE ppo_id='PPO-CHILD-1'") == [("CEASED",)]
    assert q("SELECT status FROM pensioners WHERE ppo_id='PPO-CHILD-2'") == [("IN_PAYMENT",)]
