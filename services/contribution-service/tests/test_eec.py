"""P2.26b: the Employees' Enrolment Campaign, 2026 (PIB 2300475) — a left-out employee declared, the past dues month by month
at each month's ceiling, the employee's share waived when it was not deducted, ₹100 damages, one challan crediting the member."""
from datetime import date

from tests.test_ecr_api import EST, SEED, _deliver, ctx, signatory  # noqa: F401
from tests.test_returns import pay, regular_posted

URL = "/api/v1/employers/me/eec-declarations"
UAN = "100000000777"


def dues(client, body):
    q = {k: body[k] for k in ("uan", "monthly_wages_paise", "employee_share_deducted")}
    return client.get(f"{URL}/dues", params={**q, "employee_share_deducted": str(q["employee_share_deducted"]).lower()}, headers=signatory())


def left_out(joined="2023-04-10", uan=UAN, link="AL-EEC-1"):
    from app.infra.transfers import on_member_registered
    _deliver(on_member_registered, {"uan": uan, "name": "LEFT OUT DEMO", "date_of_birth": "1995-02-01", "account_link_id": link,
                                    "member_subject": None, "establishment_id": EST, "date_of_joining": joined}, "MemberRegistered.v1")


def test_a_left_out_employee_declared_paid_and_credited(ctx, monkeypatch):
    import app.api.eec_routes as eec
    client, q = ctx
    regular_posted(client)                                                                # the seeded members are contributed for
    left_out()
    body = {"uan": UAN, "monthly_wages_paise": 1200000, "employee_share_deducted": False, "declaration": True}
    monkeypatch.setattr(eec, "today", lambda: date(2026, 6, 30))
    assert client.post(URL, json=body, headers=signatory()).json()["type"] == "/problems/campaign-closed"
    monkeypatch.setattr(eec, "today", lambda: date(2026, 10, 1))
    listing = client.get(URL, headers=signatory()).json()["data"]
    assert listing["open"] and UAN in [c["uan"] for c in listing["candidates"]]
    [(seeded,)] = q("SELECT DISTINCT m.uan FROM establishment_members m JOIN journal_lines l ON l.account_link_id=m.account_link_id LIMIT 1")
    assert seeded not in [c["uan"] for c in listing["candidates"]]                       # contributed for: not left out
    assert client.post(URL, json={**body, "uan": seeded}, headers=signatory()).json()["type"] == "/problems/not-eligible"
    assert client.post(URL, json={**body, "monthly_wages_paise": 1600000}, headers=signatory()).json()["type"] == "/problems/excluded-employee"
    preview = dues(client, body).json()["data"]
    t = preview["totals_paise"]
    assert (preview["from_month"], preview["to_month"], len(preview["months"])) == ("2023-04", "2026-03", 36)
    # ₹12,000 a month: employer 12% = ₹1,440 → EPS ₹1,000 (8.33%) + EPF ₹440; EDLI and admin ₹60 each; the employee's share waived
    assert (t["AC01_EPF_EE"], t["AC01_EPF_ER"], t["AC10_EPS"], t["AC21_EDLI"], t["AC02_ADMIN"], t["DAMAGES_14B"]) == \
        (0, 36 * 44000, 36 * 100000, 36 * 6000, 36 * 6000, 10000)
    assert t["INTEREST_7Q"] > 0 and t["TOTAL"] == sum(v for k, v in t.items() if k != "TOTAL")
    assert not q("SELECT * FROM eec_declarations")                                       # a preview records nothing
    assert client.post(URL, json=body, headers=signatory()).status_code == 428           # the amount is confirmed
    r = client.post(URL, json=body, headers=signatory({"action": "declare-eec", "resource_id": UAN, "amount_paise": t["TOTAL"]}))
    assert r.status_code == 201, r.json()
    trrn = r.json()["data"]["trrn"]
    assert q(f"SELECT kind, total_paise FROM challans WHERE trrn='{trrn}'") == [("EEC", t["TOTAL"])]
    assert dues(client, {**body, "employee_share_deducted": True}).json()["type"] == "/problems/not-eligible"   # one declaration per member ID
    pay(trrn, t["TOTAL"], "PAY-EEC-1")
    credited = dict(q("SELECT share, SUM(amount_paise) FROM journal_lines WHERE account_link_id='AL-EEC-1' GROUP BY share"))
    assert credited == {"employer": 36 * 44000}
    debit = q("SELECT SUM(amount_paise) FROM journal_lines l JOIN journals j ON j.id=l.journal_id WHERE j.kind='EEC' AND l.side='debit'")
    assert debit == [(t["TOTAL"],)]
    assert q("SELECT state FROM eec_declarations") == [("PAID",)]
    assert client.get(URL, headers=signatory()).json()["data"]["declarations"][0]["state"] == "PAID"


def test_the_ceiling_of_each_month_and_the_employee_share_when_deducted(ctx, monkeypatch):
    import app.api.eec_routes as eec
    monkeypatch.setattr(eec, "today", lambda: date(2026, 10, 1))
    client, _ = ctx
    left_out(joined="2014-06-02", uan="100000000778", link="AL-EEC-2")
    body = {"uan": "100000000778", "monthly_wages_paise": 650000, "employee_share_deducted": True}
    months = {m["wage_month"]: m for m in dues(client, body).json()["data"]["months"]}
    assert months["2014-08"]["wages_paise"] == 650000 and months["2014-09"]["wages_paise"] == 650000   # ₹6,500: within both ceilings
    assert months["2014-06"]["AC01_EPF_EE"] == 78000                                                  # deducted: payable
    assert dues(client, {**body, "monthly_wages_paise": 700000}).json()["type"] == "/problems/excluded-employee"


def test_the_employer_sees_the_past_months_on_the_employee_ledger(ctx, monkeypatch):
    import app.api.eec_routes as eec
    monkeypatch.setattr(eec, "today", lambda: date(2026, 10, 1))
    client, _ = ctx
    regular_posted(client)
    left_out(uan="100000000779", link="AL-EEC-3")
    body = {"uan": "100000000779", "monthly_wages_paise": 1000000, "employee_share_deducted": True, "declaration": True}
    t = dues(client, body).json()["data"]["totals_paise"]
    r = client.post(URL, json=body, headers=signatory({"action": "declare-eec", "resource_id": "100000000779", "amount_paise": t["TOTAL"]})).json()["data"]
    pay(r["trrn"], t["TOTAL"], "PAY-EEC-3")
    ledger = client.get("/api/v1/employers/me/members/100000000779/contribution-ledger", headers=signatory()).json()["data"]
    assert ledger["months"] == [{"wage_month": "2023-04 to 2026-03 (EEC, 2026)", "trrn": r["trrn"],
                                 "employee_paise": t["AC01_EPF_EE"], "employer_paise": t["AC01_EPF_ER"]}]
    assert t["AC01_EPF_EE"] == 36 * 120000                                    # deducted: the employee's share is paid too


def test_a_pension_in_payment_is_known_to_the_return(ctx):
    """PpoIssued.v1 (member's or disablement pension) marks the UAN; a family pension does not."""
    from app.infra.messaging import on_ppo_issued
    _, q = ctx
    _deliver(on_ppo_issued, {"ppo_id": "PPO-DEMO-0009", "pension_type": "MEMBER", "office_id": "RO-DEMO-01", "uan": "100000000777",
                             "pension_from": "2026-09-01"}, "PpoIssued.v1")
    _deliver(on_ppo_issued, {"ppo_id": "PPO-DEMO-0010", "pension_type": "SPOUSE", "office_id": "RO-DEMO-01", "uan": "100000000778",
                             "pension_from": "2026-09-01"}, "PpoIssued.v1")
    assert q("SELECT uan, ppo_id FROM eps_pensioners WHERE uan IN ('100000000777', '100000000778')") == [("100000000777", "PPO-DEMO-0009")]
    assert ("100000000901", "PPO-DEMO-0001") in q("SELECT uan, ppo_id FROM eps_pensioners")              # seeded
