"""Journey D (init.md §9, slice 4) on the running stack: a new-device login, a contact change and a claim
raise an advisory risk signal; the claim goes to an officer instead of automatic approval; a CAIU reviewer
records an outcome with no automatic action; a shared kiosk is context, not a signal; the member's account
recovery is reviewed and a session is revoked; an employer signatory is revoked.

Needs `make up migrate seed` and Playwright with Chromium:
    python -m pytest -q tests/e2e/test_journey_d_security.py
"""
import json
import time
import uuid
from pathlib import Path

import pytest

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, ensure_verified_and_granted, login, step_up, wait_for

playwright = pytest.importorskip("playwright.sync_api")

SEED = json.load(open(Path(__file__).resolve().parents[2] / "scripts" / "seed" / "synthetic.json"))
MEMBER_B = SEED["keycloak_subjects"]["member-b"]
AMOUNT = 100000            # ₹1,000: well inside the automatic limit, so only the signal sends it to an officer


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def contexts(browser):
    made = []

    def new():
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        made.append(ctx)
        return ctx
    yield new
    for c in made:
        c.close()


def as_persona(contexts, persona, return_to="/", context=None):
    page = (context or contexts()).new_page()
    login(page, persona, return_to)
    return page


def shot(page, name, path):
    SHOTS.mkdir(exist_ok=True)
    page.goto(f"{WEB}{path}")
    page.get_by_role("heading", level=1).wait_for()
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def signals(caiu):
    return call(caiu, "GET", "/api/v1/caiu/synthetic-risk-signals")[1]["data"]


def open_takeover_signal(caiu):
    return next((s for s in signals(caiu)["signals"] if s["subject_ref"] == MEMBER_B and s["status"] == "OPEN"
                 and s["detection_type"] == "NEW_DEVICE_CONTACT_CHANGE_CLAIM"), None)


def finish_leftovers(contexts, member):
    """An interrupted earlier run can leave member B with an open claim or signal; close them through the
    normal APIs (officer rejection, cash payment, CAIU review) so this run starts clean."""
    caiu = as_persona(contexts, "caiu-investigator", "/")
    for s in signals(caiu)["signals"]:
        if s["subject_ref"] == MEMBER_B and s["status"] in ("OPEN", "NEEDS_MORE_EVIDENCE"):
            call(caiu, "POST", f"/api/v1/caiu/synthetic-risk-signals/{s['signal_id']}/reviews",
                 {"outcome": "benign", "note": "Closed by the next e2e run (left open by an interrupted run)"})
    open_claims = [c for c in call(member, "GET", "/api/v1/members/me/claims")[1]["data"]
                   if c["state"] not in ("SETTLED", "REJECTED_WITH_REASON")]
    for c in open_claims:
        detail = call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]
        if detail["state"] == "AWAITING_CONFIRMATION":
            token = step_up(member, "confirm-claim", c["claim_id"], detail["version"], detail["amount_paise"])
            call(member, "POST", f"/api/v1/members/me/claims/{c['claim_id']}/confirmations", None, {"X-Step-Up-Token": token})
            detail = call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]
        if detail["state"] in ("UNDER_REVIEW", "RECOMMENDED"):
            da = as_persona(contexts, "do-caseworker", "/office/work-queue")
            case = wait_for(lambda: next((x for x in call(da, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
                                          if x["claim_id"] == c["claim_id"]), None) if detail["state"] == "UNDER_REVIEW" else True)
            if detail["state"] == "UNDER_REVIEW":
                call(da, "POST", f"/api/v1/office/cases/{case['case_id']}/recommendations",
                     {"checks": [], "note": "Closing a claim left open by an interrupted test run"})
            ss = as_persona(contexts, "ro-ss", "/office/work-queue")
            case = wait_for(lambda: next((x for x in call(ss, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
                                          if x["claim_id"] == c["claim_id"]), None))
            token = step_up(ss, "decide-case", case["case_id"], case["version"], case["amount_paise"])
            call(ss, "POST", f"/api/v1/office/cases/{case['case_id']}/decisions",
                 {"decision": "REJECT", "reason": "Test claim left open by an interrupted run"}, {"X-Step-Up-Token": token})
        elif detail["state"] in ("APPROVED", "AUTO_APPROVED", "PAYMENT_RETURNED"):
            cashier = as_persona(contexts, "ro-cashier", "/office/work-queue")
            action, path = (("reissue-payment", "reissues") if detail["state"] == "PAYMENT_RETURNED"
                            else ("instruct-payment", "payment-instructions"))

            def pay():
                tok = step_up(cashier, action, c["claim_id"], None, detail["amount_paise"])
                return call(cashier, "POST", f"/api/v1/office/claims/{c['claim_id']}/{path}", {"demo_scenario": "SUCCESS"},
                            {"X-Step-Up-Token": tok, "Idempotency-Key": str(uuid.uuid4())})[0] == 200
            wait_for(pay, timeout=20, every=1)
        wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]["state"]
                 in ("SETTLED", "REJECTED_WITH_REASON"), timeout=30)


def test_journey_d_risk_signal_review_recovery_and_revocations(contexts):
    # D1: member B signs in from a new browser (a device never seen for this account), changes contact
    # details and starts a claim.
    member = as_persona(contexts, "member-b", "/member/profile")
    finish_leftovers(contexts, member)
    time.sleep(2)   # let the benign reviews reach claim-service before this run's claim
    me = call(member, "GET", "/api/v1/members/me")[1]["data"]
    token = step_up(member, "change-contact", me["member_id"])
    status, r = call(member, "PATCH", "/api/v1/members/me/contact-details",
                     {"mobile": "9000011111", "email": "b.demo@example.org"}, {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["mobile_masked"] == "******1111", r
    status, created = call(member, "POST", "/api/v1/members/me/claims",
                           {"account_link_id": "AL-0002", "claim_type": "ADVANCE_ILLNESS", "amount_paise": AMOUNT},
                           {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 201, created
    claim = created["data"]
    assert claim["rules_applied"]["route"] == "AUTO"          # on its own this claim would be settled automatically

    # D2: the risk engine raises an advisory signal; the claim then takes the officer route.
    caiu = as_persona(contexts, "caiu-investigator", "/")
    signal = wait_for(lambda: open_takeover_signal(caiu), timeout=30)
    assert signal["advisory_only"] is True and len(signal["evidence_refs"]) == 3
    time.sleep(3)   # the signal reaches claim-service asynchronously; no member-facing API may reveal when
    c = claim["confirmation"]
    token = step_up(member, c["action"], c["resource_id"], c["resource_version"], c["amount_paise"])
    status, confirmed = call(member, "POST", f"/api/v1/members/me/claims/{claim['claim_id']}/confirmations", None,
                             {"X-Step-Up-Token": token})
    assert status == 200 and confirmed["data"]["state"] == "UNDER_REVIEW", confirmed
    assert "not an accusation" in confirmed["data"]["timeline"][-1]["note"]
    da = as_persona(contexts, "do-caseworker", "/office/work-queue")
    case = wait_for(lambda: next((x for x in call(da, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
                                  if x["claim_id"] == claim["claim_id"]), None))
    assert case["advisory_signal_id"] == signal["signal_id"]

    # D3: a kiosk shared by three people is recorded as context, never as a signal on its own.
    kiosk = contexts()
    for persona in ("member-a", "emp-preparer", "member-b"):
        as_persona(contexts, persona, "/", context=kiosk)
    shared = wait_for(lambda: signals(caiu)["shared_devices_not_signals"])
    assert shared[0]["subjects"] >= 3 and "not evidence of fraud" in shared[0]["note"]

    shot(caiu, "d2-risk-signals", "/caiu/signals")

    # D4: the reviewer records outcomes; nothing is frozen, rejected or accused automatically.
    url = f"/api/v1/caiu/synthetic-risk-signals/{signal['signal_id']}/reviews"
    status, r = call(caiu, "POST", url, {"outcome": "needs-more-evidence", "note": "Ask the member about the new phone"})
    assert status == 200 and r["data"]["automatic_actions"] == []
    status, r = call(caiu, "POST", url, {"outcome": "benign", "note": "Member confirmed a new phone and new number"})
    assert status == 200 and r["data"]["status"] == "BENIGN"
    assert call(member, "GET", f"/api/v1/members/me/claims/{claim['claim_id']}")[1]["data"]["state"] == "UNDER_REVIEW"

    # The officers finish the claim normally (DA → SS for this amount); the cash section pays it.
    status, _ = call(da, "POST", f"/api/v1/office/cases/{case['case_id']}/recommendations",
                     {"checks": ["KYC verified"], "note": "Risk signal reviewed as benign by CAIU"})
    assert status == 200
    ss = as_persona(contexts, "ro-ss", "/office/work-queue")
    case = wait_for(lambda: next((x for x in call(ss, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
                                  if x["claim_id"] == claim["claim_id"]), None))
    token = step_up(ss, "decide-case", case["case_id"], case["version"], case["amount_paise"])
    status, r = call(ss, "POST", f"/api/v1/office/cases/{case['case_id']}/decisions", {"decision": "APPROVE", "reason": None},
                     {"X-Step-Up-Token": token})
    assert status == 200, r
    cashier = as_persona(contexts, "ro-cashier", "/office/work-queue")

    def pay():
        tok = step_up(cashier, "instruct-payment", claim["claim_id"], None, AMOUNT)
        s, _ = call(cashier, "POST", f"/api/v1/office/claims/{claim['claim_id']}/payment-instructions",
                    {"demo_scenario": "SUCCESS"}, {"X-Step-Up-Token": tok, "Idempotency-Key": str(uuid.uuid4())})
        return s == 200
    wait_for(pay, timeout=20, every=1)
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{claim['claim_id']}")[1]["data"]["state"] == "SETTLED",
             timeout=30)

    # D5a: the member asks for account recovery; a security analyst reviews it and it restores the
    # verified contact details; the analyst then revokes the session left open on the kiosk.
    token = step_up(member, "request-recovery", me["member_id"])
    status, rec = call(member, "POST", "/api/v1/members/me/account-recovery-requests",
                       {"reason": "I want my old verified number back after the change"}, {"X-Step-Up-Token": token})
    assert status in (201, 409), rec
    analyst = as_persona(contexts, "security-analyst", "/security/activity")
    queue = call(analyst, "GET", "/api/v1/security/account-recovery-requests")[1]["data"]
    pending = next(q for q in queue if q["state"] == "PENDING_REVIEW" and q["member_id"] == me["member_id"])
    assert pending["restore_to"]["mobile_masked"] == SEED["members"][1]["mobile_masked"]
    shot(analyst, "d5-sessions-recovery", "/security/sessions")
    token = step_up(analyst, "decide-recovery", pending["request_id"])
    status, r = call(analyst, "POST", f"/api/v1/security/account-recovery-requests/{pending['request_id']}/decisions",
                     {"decision": "APPROVE", "note": "Verified with the member on the registered number"}, {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    assert call(member, "GET", "/api/v1/members/me")[1]["data"]["mobile_masked"] == SEED["members"][1]["mobile_masked"]
    kiosk_page = kiosk.pages[-1]                                   # member B is still signed in on the kiosk
    sessions = call(analyst, "GET", "/api/v1/security/sessions")[1]["data"]
    own = {s["session_id"] for s in call(member, "GET", "/api/v1/members/me/sessions")[1]["data"] if s["current"]}
    target = next(s for s in sessions if s["subject"] == MEMBER_B and s["session_id"] not in own)
    token = step_up(analyst, "revoke-session", target["session_id"])
    status, r = call(analyst, "POST", f"/api/v1/security/sessions/{target['session_id']}/revocations", None,
                     {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["revoked"] is True
    assert call(kiosk_page, "GET", "/api/v1/members/me")[0] == 401
    assert call(member, "GET", "/api/v1/members/me")[0] == 200            # the member's own session is untouched

    shot(member, "d5-member-security", "/member/security")

    # D5b: the employer owner revokes the authorised signatory; the signatory is refused within 5 seconds.
    owner = as_persona(contexts, "emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    signatory = as_persona(contexts, "emp-signatory", "/employer")
    assert call(signatory, "GET", "/api/v1/employers/me/challans")[0] == 200
    grant = next(g for g in call(owner, "GET", "/api/v1/employers/me/signatories")[1]["data"]
                 if g["username"] == "emp-signatory" and g["status"] == "ACTIVE")
    token = step_up(owner, "revoke-signatory", grant["grant_id"])
    status, r = call(owner, "POST", f"/api/v1/employers/me/signatories/{grant['grant_id']}/revocations",
                     {"reason": "Signatory left the company"}, {"X-Step-Up-Token": token})
    assert status == 200, r
    revoked_at = time.time()
    wait_for(lambda: call(signatory, "GET", "/api/v1/employers/me/challans")[0] in (401, 403), timeout=5, every=0.25)
    assert time.time() - revoked_at <= 5
    ensure_verified_and_granted(owner)                                     # leave the demo usable
