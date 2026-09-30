"""Policy changes that move money, on the running stack (no code change, no redeploy):

1. Interest — the rate declared for 2025-26 is revised; Finance (FA & CAO) re-runs annual interest crediting and
   only the difference is credited; the member's passbook shows the revision.
2. TDS — the TDS rate on withdrawals (with a verified PAN) is changed; the next final settlement paid is taxed at the
   new rate, the member receives the net amount.
3. Pension — the minimum pension is raised for pensions in payment with retrospective effect; pension-service
   proposes the revision, an APFC (Pension) approves it with step-up, the pensioner sees the new amount and arrears.

Each change is drafted by the ACC (HQ) and published by the CPFC (maker-checker, one-time code). If a version is
already scheduled for a later date, it is amended first (same date) so it does not undo today's change.
"""
import copy
import uuid
from datetime import UTC, date, datetime

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, detail, persona, rule_sets  # noqa: F401  (fixtures)

AMOUNT = 6000000                      # ₹60,000 final settlement: above the ₹50,000 TDS threshold, settled automatically


def today() -> date:
    return datetime.now(UTC).date()


def _publish_from(drafter, approver, base: dict, change, effective: str, note: str) -> dict:
    doc = copy.deepcopy(detail(drafter, base["version_id"])["document"])
    change(doc)
    status, created = call(drafter, "POST", "/api/v1/ho/config/rule-sets", {
        "base_version_id": base["version_id"], "rule_version": f"e2e-{effective}-{uuid.uuid4().hex[:6]}", "effective_from": effective,
        "change_note": note, "document": doc})
    assert status == 201 and created["data"]["checks"] == [], created
    vid = created["data"]["version_id"]
    status, submitted = call(drafter, "POST", f"/api/v1/ho/config/rule-sets/{vid}/submissions")
    assert status == 200, submitted
    token = step_up(approver, "publish-policy", vid, submitted["data"]["version"])
    status, decided = call(approver, "POST", f"/api/v1/ho/config/rule-sets/{vid}/decisions",
                           {"decision": "APPROVE", "note": f"Approved: {note}"}, {"X-Step-Up-Token": token})
    assert status == 200, decided
    return decided["data"]


def publish_today(persona, change, note: str) -> dict:
    """Publish `change` from today; first carry it into any version already scheduled for a later date."""
    drafter, approver = persona("ho-policy", "/policy"), persona("ho-analyst", "/policy")
    items = rule_sets(drafter)
    carried = [_publish_from(drafter, approver, later, change, later["effective_from"], f"{note} (carried into the scheduled version)")["rule_version"]
               for later in sorted((i for i in items if i["status"] == "SCHEDULED"), key=lambda i: i["effective_from"], reverse=True)]
    in_force = next(i for i in rule_sets(drafter) if i["status"] == "IN_FORCE")
    published = _publish_from(drafter, approver, in_force, change, today().isoformat(), note)
    assert published["status"] == "IN_FORCE", published
    return {**published, "carrying": [published["rule_version"], *carried]}


def in_force_document(persona) -> dict:
    drafter = persona("ho-policy", "/policy")
    return detail(drafter, next(i for i in rule_sets(drafter) if i["status"] == "IN_FORCE")["version_id"])["document"]


def test_revised_interest_rate_credits_only_the_difference(persona):
    finance = persona("ho-finance", "/finance/interest")
    url = "/api/v1/office/accounts/interest-postings"

    def plan():
        return call(finance, "GET", f"{url}?financialYear=2025-26")[1]["data"]

    def run(p):
        token = step_up(finance, "post-interest", "2025-26", None, abs(p["total_to_credit_paise"]))
        status, body = call(finance, "POST", url, {"financial_year": "2025-26"}, {"X-Step-Up-Token": token})
        assert status == 200, body
        return body["data"]

    p = plan()
    if p["total_to_credit_paise"]:                                     # first run on this stack: credit the year
        run(p)
    assert plan()["total_to_credit_paise"] == 0
    current = p["rate_bp"]
    revised = 850 if current == 825 else (current + 5 if current < 1000 else 825)
    published = publish_today(persona, lambda d: d["interest"]["rates_bp"].update({"2025-26": revised}),
                              f"Interest for 2025-26 revised to {revised / 100}% (illustrative)")
    assert [i["financial_year"] for i in published["preview"]["interest"]] == ["2025-26"]
    p = wait_for(lambda: (lambda x: x if x["rate_bp"] == revised else None)(plan()), timeout=30)
    b = next(a for a in p["accounts"] if a["account_link_id"] == "AL-0002")
    assert b["employee"]["due_paise"] == 3000000 * revised // 10000                 # ₹30,000 held all year
    assert b["employee"]["now_paise"] == 3000000 * (revised - current) // 10000     # only the difference
    SHOTS.mkdir(exist_ok=True)
    finance.goto(f"{WEB}/finance/interest")
    finance.get_by_role("heading", name="Annual interest crediting").wait_for()
    finance.screenshot(path=str(SHOTS / "interest-revision.png"), full_page=True)
    done = run(p)
    assert done["revision"] is True and done["rate_bp"] == revised

    member = persona("member-b", "/member/passbook")
    entries = wait_for(lambda: (lambda es: es if any(f"revised to {revised / 100:g}%" in e["description"] for e in es) else None)(
        call(member, "GET", "/api/v1/members/me/passbook")[1]["data"]["accounts"][0]["entries"]), timeout=30)
    assert entries[0]["kind"] == "OPENING_BALANCE" and entries[1]["kind"] == "INTEREST"


def test_changed_tds_rate_applies_to_the_next_payment(persona):
    member, cashier = persona("member-c", "/member/claims"), persona("ro-cashier", "/office/work-queue")

    def settle() -> dict:
        status, created = call(member, "POST", "/api/v1/members/me/claims",
                               {"account_link_id": "AL-0006", "claim_type": "FINAL_SETTLEMENT", "amount_paise": AMOUNT},
                               {"Idempotency-Key": str(uuid.uuid4())})
        assert status == 201, created
        c = created["data"]
        conf = c["confirmation"]
        token = step_up(member, conf["action"], conf["resource_id"], conf["resource_version"], conf["amount_paise"])
        status, confirmed = call(member, "POST", f"/api/v1/members/me/claims/{c['claim_id']}/confirmations", None, {"X-Step-Up-Token": token})
        assert status == 200 and confirmed["data"]["state"] == "AUTO_APPROVED", confirmed
        wait_for(lambda: call(cashier, "POST", f"/api/v1/office/claims/{c['claim_id']}/payment-instructions", {"demo_scenario": "SUCCESS"},
                              {"X-Step-Up-Token": step_up(cashier, "instruct-payment", c["claim_id"], None, AMOUNT),
                               "Idempotency-Key": str(uuid.uuid4())})[0] == 200, timeout=30, every=1)
        return wait_for(lambda: (lambda d: d if d["state"] == "SETTLED" else None)(
            call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]), timeout=30)

    before = in_force_document(persona)["tds"]["rate_with_pan_bp"]
    first = settle()
    assert first["tax"]["rate_bp"] == before and first["tax"]["tds_paise"] == AMOUNT * before // 10000
    assert first["tax"]["net_paise"] == AMOUNT - first["tax"]["tds_paise"]

    after = 500 if before != 500 else 1000
    published = publish_today(persona, lambda d: d["tds"].update(rate_with_pan_bp=after), f"TDS with a PAN set to {after / 100:g}% (illustrative)")
    assert any(r["pan"] == "verified" for r in published["preview"]["tds"])
    second = wait_for(lambda: (lambda d: d if d["tax"]["rate_bp"] == after else None)(settle()), timeout=60, every=2)
    assert second["tax"]["tds_paise"] == AMOUNT * after // 10000 and second["tax"]["rule_version"] == published["rule_version"]
    member.goto(f"{WEB}/member/claims/{second['claim_id']}")
    member.get_by_text("Income tax deducted (TDS)").wait_for()
    member.screenshot(path=str(SHOTS / "tds-on-final-settlement.png"), full_page=True)
    notices = wait_for(lambda: [n for n in call(member, "GET", "/api/v1/members/me/notifications")[1]["data"]
                                if n["reference_id"] == second["claim_id"] and n["template"] == "CLAIM_SETTLED"], timeout=30)
    assert "deducted at source" in notices[0]["body"]


def test_higher_minimum_pension_revises_pensions_in_payment_with_arrears(persona):
    pensioner, apfc = persona("pensioner-a", "/pensioner"), persona("ro-pension", "/office/pension-revisions")
    me = call(pensioner, "GET", "/api/v1/pensioners/me")[1]["data"]
    minimum = max(in_force_document(persona)["pension"]["minimum_pension_paise"], me["monthly_paise"]) + 10000     # ₹100 more
    t = today()
    back = date(t.year - (t.month <= 2), (t.month - 3) % 12 + 1, 1)                  # the first of two months ago

    def change(d):
        d["pension"].update(minimum_pension_paise=minimum, applies_to_pensions_in_payment=True, revise_in_payment_from=back.isoformat())
    published = publish_today(persona, change, f"Minimum pension raised to ₹{minimum // 100:,} for pensions in payment from {back} (illustrative)")
    assert "revised from" in published["preview"]["pensions_in_payment"]

    def proposed():
        items = call(apfc, "GET", "/api/v1/office/pensions/revisions")[1]["data"]["items"]
        return next((r for r in items if r["ppo_id"] == "PPO-DEMO-0001" and r["new_monthly_paise"] == minimum), None)
    r = wait_for(proposed, timeout=30)
    assert r["old_monthly_paise"] == me["monthly_paise"] and r["effective_from"] == back.isoformat()
    assert r["arrears_paise"] >= 2 * (minimum - me["monthly_paise"])                  # the two months already paid
    apfc.goto(f"{WEB}/office/pension-revisions")
    apfc.get_by_role("heading", name="Pension revisions", exact=True).wait_for()
    apfc.screenshot(path=str(SHOTS / "pension-revision-queue.png"), full_page=True)
    token = step_up(apfc, "approve-pension-revision", r["revision_id"], None, r["arrears_paise"])
    status, done = call(apfc, "POST", "/api/v1/office/pensions/PPO-DEMO-0001/revisions",
                        {"revision_id": r["revision_id"], "decision": "APPROVE", "note": "Minimum pension notification applied"},
                        {"X-Step-Up-Token": token})
    assert status == 200 and done["data"]["state"] == "APPROVED", done
    me = call(pensioner, "GET", "/api/v1/pensioners/me")[1]["data"]
    assert me["monthly_paise"] == minimum and me["rule_version"] in published["carrying"]   # any version carrying the change
    paid = call(pensioner, "GET", "/api/v1/pensioners/me/payments")[1]["data"]
    assert paid[0]["kind"] == "ARREARS" and paid[0]["amount_paise"] == r["arrears_paise"]
    pensioner.goto(f"{WEB}/pensioner")
    pensioner.locator("main").get_by_text("Arrears").first.wait_for()   # not the persona picker's hidden descriptions
    pensioner.screenshot(path=str(SHOTS / "pensioner-revised.png"), full_page=True)
