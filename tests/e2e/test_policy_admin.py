"""Policy administration on the running stack: a change published through the UI roles takes effect in the
services without code or redeploys.

1. A new claim type in force today — an advance for building a house, always decided by officers, with its
   own chain DA → AO → APFC. A member claims it and the officers of that chain decide it.
2. The EPS/EDLI wage ceiling raised from ₹15,000 to ₹25,000 from the first of next month. Returns for months
   before that date are still checked against ₹15,000; returns from that month against ₹25,000.

Both are published by the CPFC after the ACC (HQ) drafts them (maker-checker, one-time code). On a rerun the
already published versions are reused.
"""
import copy
import random
import uuid
from datetime import date

import pytest

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, ensure_verified_and_granted, login, step_up, wait_for

playwright = pytest.importorskip("playwright.sync_api")
HOUSING = {"form_type": "31", "label": "Advance for building a house",
           "plain_rule": "Up to 90% of your balance after 3 years of service, while still employed. Always decided by officers.",
           "requires_active_employment": True, "min_service_months": 36, "max_from": "total_balance", "max_pct_bp": 9000,
           "auto_settle_up_to_paise": None,
           "approval_bands": [{"upto_paise": None, "chain": ["fo.da_accounts", "fo.ao", "fo.apfc"]}]}


def first_of_next_month() -> date:
    t = date.today()
    return date(t.year + (t.month == 12), t.month % 12 + 1, 1)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def persona(browser):
    made = []

    def make(name, return_to="/"):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        made.append(ctx)
        page = ctx.new_page()
        login(page, name, return_to)
        return page
    yield make
    for c in made:
        c.close()


def rule_sets(page):
    return call(page, "GET", "/api/v1/ho/config/rule-sets")[1]["data"]["items"]


def detail(page, version_id):
    return call(page, "GET", f"/api/v1/ho/config/rule-sets/{version_id}")[1]["data"]


def publish(drafter, approver, change, effective: date, note: str) -> dict:
    """Draft from the version in force, check, submit, and publish as the CPFC. Returns the published detail."""
    in_force = next(i for i in rule_sets(drafter) if i["status"] == "IN_FORCE")
    doc = copy.deepcopy(detail(drafter, in_force["version_id"])["document"])
    change(doc)
    name = f"e2e-{effective.isoformat()}-{uuid.uuid4().hex[:6]}"
    status, created = call(drafter, "POST", "/api/v1/ho/config/rule-sets", {
        "base_version_id": in_force["version_id"], "rule_version": name, "effective_from": effective.isoformat(),
        "change_note": note, "document": doc})
    assert status == 201 and created["data"]["checks"] == [], created
    vid = created["data"]["version_id"]
    status, submitted = call(drafter, "POST", f"/api/v1/ho/config/rule-sets/{vid}/submissions")
    assert status == 200, submitted
    assert call(drafter, "POST", f"/api/v1/ho/config/rule-sets/{vid}/decisions", {"decision": "APPROVE", "note": "maker is not checker"})[0] == 403
    token = step_up(approver, "publish-policy", vid, submitted["data"]["version"])
    status, decided = call(approver, "POST", f"/api/v1/ho/config/rule-sets/{vid}/decisions",
                           {"decision": "APPROVE", "note": f"Approved: {note}"}, {"X-Step-Up-Token": token})
    assert status == 200, decided
    return decided["data"]


def test_new_claim_type_with_its_own_chain_reaches_members_and_officers(persona):
    drafter, approver = persona("ho-policy", "/policy"), persona("ho-analyst", "/policy")
    in_force = next(i for i in rule_sets(drafter) if i["status"] == "IN_FORCE")
    if "ADVANCE_HOUSING" not in detail(drafter, in_force["version_id"])["document"]["claims"]["types"]:
        published = publish(drafter, approver, lambda d: d["claims"]["types"].update(ADVANCE_HOUSING=HOUSING), date.today(),
                            "Introduce an advance for building a house (illustrative)")
        assert published["status"] == "IN_FORCE"
        rows = {(c["claim_type"], c["amount"]): c for c in published["preview"]["claims"]}
        assert rows[("ADVANCE_HOUSING", "₹20,000")]["after"] == "DA → AO → APFC"

    member = persona("member-b", "/member/claims")
    types = wait_for(lambda: (lambda t: t if "ADVANCE_HOUSING" in t else None)(
        {t["claim_type"]: t for t in call(member, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]["accounts"][0]["types"]}),
        timeout=30)
    assert types["ADVANCE_HOUSING"]["eligible"], types["ADVANCE_HOUSING"]
    status, created = call(member, "POST", "/api/v1/members/me/claims",
                           {"account_link_id": "AL-0002", "claim_type": "ADVANCE_HOUSING", "amount_paise": 100000},
                           {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 201, created
    c = created["data"]
    assert c["rules_applied"]["route"] == "REVIEW"                      # ₹1,000, yet always decided by officers
    assert c["rules_applied"]["approval_chain"] == ["Dealing assistant (accounts)", "Accounts officer", "Assistant PF commissioner"]
    conf = c["confirmation"]
    token = step_up(member, conf["action"], conf["resource_id"], conf["resource_version"], conf["amount_paise"])
    assert call(member, "POST", f"/api/v1/members/me/claims/{c['claim_id']}/confirmations", None, {"X-Step-Up-Token": token})[0] == 200

    def my_case(page):
        return next((x for x in call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"] if x["claim_id"] == c["claim_id"]), None)
    da = persona("do-caseworker", "/office/work-queue")
    case = wait_for(lambda: my_case(da), timeout=30)
    assert case["chain"] == ["fo.da_accounts", "fo.ao", "fo.apfc"]
    from tests.e2e.officers import decide, recommend
    assert recommend(da, case, "Policy e2e")[0] == 200
    for who, path in (("ro-ao", "decisions"), ("ro-apfc", "second-approvals")):
        page = persona(who, "/office/work-queue")
        case = wait_for(lambda: my_case(page), timeout=30)
        status, r = decide(page, case, path)
        assert status == 200, r
    cashier = persona("ro-cashier", "/office/work-queue")
    wait_for(lambda: call(cashier, "POST", f"/api/v1/office/claims/{c['claim_id']}/payment-instructions", {"demo_scenario": "SUCCESS"},
                          {"X-Step-Up-Token": step_up(cashier, "instruct-payment", c["claim_id"], None, 100000),
                           "Idempotency-Key": str(uuid.uuid4())})[0] == 200, timeout=30, every=1)
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]["state"] == "SETTLED", timeout=30)


def test_wage_ceiling_raised_from_next_month(persona):
    drafter, approver = persona("ho-policy", "/policy"), persona("ho-analyst", "/policy")
    effective = first_of_next_month()
    scheduled = next((i for i in rule_sets(drafter) if i["status"] in ("SCHEDULED", "IN_FORCE") and i["effective_from"] == effective.isoformat()), None)
    if scheduled is None:
        published = publish(drafter, approver, lambda d: d["contribution"].update(eps_wage_ceiling_paise=2500000, edli_wage_ceiling_paise=2500000),
                            effective, "Wage ceiling raised from ₹15,000 to ₹25,000 (illustrative notification)")
        row = next(x for x in published["preview"]["contribution"] if x["monthly_wages"] == "₹20,000")
        assert row["before"]["employer_eps"] == "₹1,250" and row["after"]["employer_eps"] == "₹1,666"
        vid = published["version_id"]
    else:
        vid = scheduled["version_id"]
    SHOTS.mkdir(exist_ok=True)
    drafter.goto(f"{WEB}/policy/{vid}")
    drafter.get_by_role("heading", name="Effect, with worked examples").wait_for()
    drafter.screenshot(path=str(SHOTS / "policy-ceiling-change.png"), full_page=True)

    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    operator = persona("emp-preparer", "/employer/ecr")
    member = {"uan": "100000000001", "name": "ASHA DEMO"}
    ee, eps = 2400, round(20000 * 0.0833)
    line = "#~#".join(map(str, [member["uan"], member["name"], 20000, 20000, 20000, 20000, ee, eps, ee - eps, 0, 0]))

    def file_for(month: str) -> dict:
        status, body = call(operator, "POST", "/api/v1/employers/me/ecr-filings", {"wage_month": month, "format": "ECR_TXT", "content": line})
        assert status == 201, body
        return body["data"]
    old = file_for(f"{random.randint(2001, 2019)}-{random.randint(1, 12):02d}")          # before the change
    new = wait_for(lambda: (lambda d: d if d["validation_report"]["valid"] else None)(
        file_for(f"{random.randint(2031, 2039)}-{random.randint(1, 12):02d}")), timeout=30, every=2)   # after it
    assert not old["validation_report"]["valid"] and any(i["code"] == "E-EPS-CEILING" for i in old["validation_report"]["issues"])
    assert new["filing"]["rule_version"] != old["filing"]["rule_version"]
