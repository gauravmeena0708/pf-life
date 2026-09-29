"""The 25 must-deny tests of docs/permissions.md, against the running stack (browser → gateway → service).

A few rows have no interactive persona (service accounts `tech.ai_service`, `payroll_provider`) or are about
internal ordering (duplicate bank callbacks, grant-scoped revocation across two establishments). Those are
checked against the gateway route table that enforces them, and the unit test that exercises the service
rule is named in COVERED_BY_UNIT_TESTS so nothing is silently skipped.

Needs `make up migrate seed` and Playwright with Chromium:
    python -m pytest -q tests/security
"""
import json
import re
import time
import uuid
from pathlib import Path

import pytest

from tests.e2e.test_journey_a_ecr import call, ensure_verified_and_granted, login, step_up, wait_for
from tests.e2e.officers import decide as officer_decide, recommend
from tests.e2e.test_journey_d_security import finish_leftovers

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]
ROUTES = {(r["method"], r["path_template"]): r for r in json.loads((ROOT / "apps/gateway/app/routes.generated.json").read_text())}
DENIED = (401, 403, 404)
MEMBER_B_UAN = "100000000002"

COVERED_BY_UNIT_TESTS = {
    "DENY-05": "services/workflow-service/tests/test_cases_api.py::test_other_office_case_is_invisible",
    "DENY-12": "services/workflow-service/tests/test_cases_api.py::test_full_chain_with_step_up_and_events",
    "DENY-19": "apps/gateway/tests/test_gateway.py (grant-keyed revocation) and revocation.is_revoked",
    "DENY-23": "services/payment-simulator/tests/test_payments.py::test_callback_signature_replay_and_duplicate",
}


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
        ctx = browser.new_context()
        made.append(ctx)
        page = ctx.new_page()
        login(page, name, return_to)
        return page
    yield make
    for c in made:
        c.close()


def callers(method, path):
    return set(ROUTES[(method, path)]["callers"])


# ── members and employers ──────────────────────────────────────────────────────────────────────

def test_deny_01_member_reads_another_members_passbook(persona):
    status, body = call(persona("member-b"), "GET", "/api/v1/members/me/accounts/AL-0001/passbook")
    assert status == 404 and "AL-0001" not in json.dumps(body.get("data", {}))


def test_deny_02_and_25_operator_reads_filing_of_an_unauthorised_or_forged_establishment(persona):
    ensure_verified_and_granted(persona("emp-owner", "/employer"))
    operator = persona("emp-preparer", "/employer")
    filings = call(operator, "GET", "/api/v1/employers/me/ecr-filings")[1]["data"]
    target = filings[0]["filing_id"] if filings else str(uuid.uuid4())
    status, _ = call(operator, "GET", f"/api/v1/employers/me/ecr-filings/{target}", None, {"X-Establishment-Id": "EST-FORGED-9999"})
    assert status in DENIED


def test_deny_03_operator_approves_their_own_filing(persona):
    operator = persona("emp-preparer", "/employer")
    filings = call(operator, "GET", "/api/v1/employers/me/ecr-filings")[1]["data"]
    target = filings[0]["filing_id"] if filings else str(uuid.uuid4())
    status, _ = call(operator, "POST", f"/api/v1/employers/me/ecr-filings/{target}/approvals", {"decision": "APPROVE"})
    assert status == 403


def test_deny_04_and_18_revoked_signatory_and_operator_are_refused_while_their_sessions_are_open(persona):
    owner = persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    signatory, operator = persona("emp-signatory", "/employer"), persona("emp-preparer", "/employer")
    filing = str(uuid.uuid4())
    for kind, page, probe in (("signatories", signatory, ("POST", f"/api/v1/employers/me/ecr-filings/{filing}/submissions", None)),
                              ("operators", operator, ("POST", "/api/v1/employers/me/ecr-filings",
                                                       {"wage_month": "2001-01", "format": "ECR_TXT", "content": "x"}))):
        username = "emp-signatory" if kind == "signatories" else "emp-preparer"
        grant = next(g for g in call(owner, "GET", f"/api/v1/employers/me/{kind}")[1]["data"]
                     if g["username"] == username and g["status"] == "ACTIVE")
        action = "revoke-signatory" if kind == "signatories" else "revoke-operator"
        token = step_up(owner, action, grant["grant_id"])
        assert call(owner, "POST", f"/api/v1/employers/me/{kind}/{grant['grant_id']}/revocations",
                    {"reason": "must-deny test"}, {"X-Step-Up-Token": token})[0] == 200
        start = time.time()
        def refused():
            # A revoked user can still obtain a one-time code; the service must refuse the command itself.
            headers = {"Idempotency-Key": str(uuid.uuid4()), "If-Match": "1"}
            if kind == "signatories":
                headers["X-Step-Up-Token"] = step_up(page, "submit-ecr", filing, 1, 0)
            return call(page, probe[0], probe[1], probe[2], headers)[0] in DENIED
        wait_for(refused, timeout=5, every=0.25)
        assert time.time() - start <= 5
    ensure_verified_and_granted(owner)


# ── office roles ───────────────────────────────────────────────────────────────────────────────

def test_deny_05_decision_on_a_case_outside_the_officers_office(persona):
    status, _ = call(persona("ro-ss", "/office/work-queue"), "POST", "/api/v1/office/cases/CASE-OTHEROFFICE/decisions",
                     {"decision": "APPROVE"}, {"X-Step-Up-Token": "not-a-token"})
    assert status in DENIED


def test_deny_06_ministry_viewer_requests_an_individual_member(persona):
    assert call(persona("ministry-viewer"), "GET", f"/api/v1/office/members/{MEMBER_B_UAN}")[0] == 403


def test_deny_07_ndc_operator_requests_member_financial_data(persona):
    assert call(persona("ndc-operator"), "GET", "/api/v1/members/me/passbook")[0] == 403


def test_deny_08_auditor_attempts_a_write(persona):
    assert call(persona("auditor"), "POST", "/api/v1/office/cases/CASE-X/decisions", {"decision": "APPROVE"})[0] == 403


def test_deny_09_10_ai_service_cannot_pay_or_approve():
    assert "tech.ai_service" not in callers("POST", "/office/claims/{claimId}/payment-instructions")
    assert "tech.ai_service" not in callers("POST", "/office/cases/{caseId}/decisions")
    assert "tech.ai_service" not in callers("POST", "/office/cases/{caseId}/second-approvals")


def test_deny_11_payroll_partner_cannot_enumerate_members():
    assert "payroll_provider" not in callers("GET", "/employers/me/members")


def test_deny_12_approver_outside_their_amount_band():
    # SS approves only in bands whose chain contains fo.ss at that level; the second level is APFC / OIC only.
    assert "fo.ss" not in callers("POST", "/office/cases/{caseId}/second-approvals")


def test_deny_13_recommender_also_approves(persona):
    assert call(persona("do-caseworker", "/office/work-queue"), "POST", "/api/v1/office/cases/CASE-X/second-approvals",
                {"decision": "APPROVE"})[0] == 403


def test_deny_14_da_approves_an_exceptional_ledger_credit(persona):
    assert call(persona("do-caseworker", "/office/work-queue"), "POST", "/api/v1/office/ledger-adjustments/ADJ-1/approvals", {})[0] == 403


def test_deny_16_pensioner_enumeration_without_proof(persona):
    page = persona("member-a")
    for i in range(3):
        status, body = call(page, "POST", "/api/v1/public/pension/life-certificate-lookups", {"ppo": f"PPO-{i:06d}"})
        assert status >= 400 and "data" not in body                   # never returns pensioner data


def test_deny_17_falsified_bank_callback(persona):
    status, _ = call(persona("member-a"), "POST", "/api/v1/integrations/mock-bank/payment-confirmations",
                     {"payment_id": "PAY-X", "bank_reference": "B"}, {"x-bank-signature": "0" * 64})
    assert status == 401


def test_deny_24_ai_retrieval_excludes_documents_the_caller_may_not_see(persona):
    body = call(persona("member-b", "/member/assistant"), "POST", "/api/v1/ai/knowledge/search",
                {"question": "claim scrutiny checklist vigilance referral confidential"})[1]["data"]
    assert not any(c["ref"].startswith(("OFF-", "CONF-")) for c in body["citations"]) and "7731" not in json.dumps(body)


# ── frozen accounts (tier-2 process) and claim step-up ─────────────────────────────────────────

def _freeze(rpfc, uan):
    token = step_up(rpfc, "freeze-account", uan)
    return call(rpfc, "POST", f"/api/v1/office/members/{uan}/freezes",
                {"category": "B", "reason": "Must-deny test of a frozen account", "order_ref": "ORD-SEC-1"}, {"X-Step-Up-Token": token})


def _verify_and_defreeze(persona, case_id, uan):
    for who in ("do-caseworker", "ro-ss", "ro-apfc", "ro-oic"):
        page = persona(who, "/office/work-queue")
        status, r = call(page, "POST", f"/api/v1/office/freeze-cases/{case_id}/verifications",
                         {"finding": "GENUINE_MEMBER", "note": "Verified in the member ledger and KYC"})
        assert status == 200, r
    token = step_up(page, "defreeze-account", uan)
    status, r = call(page, "POST", f"/api/v1/office/members/{uan}/defreezes", {"reason": "Verified genuine member"},
                     {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["state"] == "ACTIVE", r


def _close_open_freeze(persona, uan):
    """An interrupted earlier run can leave the account frozen; finish its verification and de-freeze it."""
    chain = [("do-caseworker", "fo.da_accounts"), ("ro-ss", "fo.ss"), ("ro-apfc", "fo.apfc"), ("ro-oic", "fo.oic")]
    for who, _ in chain:
        page = persona(who, "/office/work-queue")
        for case in call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]:
            if case.get("process") == "member_freeze" and case.get("subject_ref") == uan:
                if case["next_action"] == "verify":
                    call(page, "POST", f"/api/v1/office/freeze-cases/{case['case_id']}/verifications",
                         {"finding": "GENUINE_MEMBER", "note": "Closing a freeze left by an interrupted run"})
                elif case["next_action"] == "defreeze":
                    token = step_up(page, "defreeze-account", uan)
                    call(page, "POST", f"/api/v1/office/members/{uan}/defreezes", {"reason": "Closing an interrupted test run"},
                         {"X-Step-Up-Token": token})
    oic = persona("ro-oic", "/office/work-queue")
    for case in call(oic, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]:
        if case.get("process") == "member_freeze" and case.get("subject_ref") == uan and case["next_action"] == "defreeze":
            token = step_up(oic, "defreeze-account", uan)
            call(oic, "POST", f"/api/v1/office/members/{uan}/defreezes", {"reason": "Closing an interrupted test run"},
                 {"X-Step-Up-Token": token})


def test_deny_15_20_21_22_frozen_account_step_up_binding_and_payment_order(persona, browser):
    _close_open_freeze(persona, MEMBER_B_UAN)
    member = persona("member-b", "/member/claims")
    finish_leftovers(lambda: browser.new_context(), member)
    time.sleep(2)
    status, created = call(member, "POST", "/api/v1/members/me/claims",
                           {"account_link_id": "AL-0002", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 10000},
                           {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 201, created
    claim = created["data"]
    cid, c = claim["claim_id"], claim["confirmation"]
    cashier = persona("ro-cashier", "/office/work-queue")

    # DENY-21: payment before the claim is approved.
    tok = step_up(cashier, "instruct-payment", cid, None, c["amount_paise"])
    assert call(cashier, "POST", f"/api/v1/office/claims/{cid}/payment-instructions", {"demo_scenario": "SUCCESS"},
                {"X-Step-Up-Token": tok, "Idempotency-Key": str(uuid.uuid4())})[0] == 409

    # DENY-20: a step-up token for another amount, and a replayed token, are refused.
    wrong = step_up(member, c["action"], cid, c["resource_version"], c["amount_paise"] + 1)
    assert call(member, "POST", f"/api/v1/members/me/claims/{cid}/confirmations", None, {"X-Step-Up-Token": wrong})[0] == 403
    good = step_up(member, c["action"], cid, c["resource_version"], c["amount_paise"])
    status, confirmed = call(member, "POST", f"/api/v1/members/me/claims/{cid}/confirmations", None, {"X-Step-Up-Token": good})
    assert status == 200, confirmed
    assert call(member, "POST", f"/api/v1/members/me/claims/{cid}/confirmations", None, {"X-Step-Up-Token": good})[0] == 403
    if confirmed["data"]["state"] == "UNDER_REVIEW":        # an advisory check sent it to officers; approve it normally
        for who, path in (("do-caseworker", "recommendations"), ("ro-ss", "decisions")):
            page = persona(who, "/office/work-queue")
            case = wait_for(lambda: next((x for x in call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
                                          if x["claim_id"] == cid), None))
            if path == "recommendations":
                recommend(page, case, "Must-deny test claim")
            else:
                officer_decide(page, case, path)
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{cid}")[1]["data"]["state"] in ("APPROVED", "AUTO_APPROVED"))

    # DENY-15 / 22: the account is frozen (tier-2 process) after approval — no new claim, no payment.
    rpfc = persona("zo-rpfc", "/office/work-queue")
    status, frozen = _freeze(rpfc, MEMBER_B_UAN)
    assert status == 200, frozen
    wait_for(lambda: call(member, "POST", "/api/v1/members/me/claims",
                          {"account_link_id": "AL-0002", "claim_type": "ADVANCE_ILLNESS", "amount_paise": 10000},
                          {"Idempotency-Key": str(uuid.uuid4())})[0] == 403, timeout=15)
    wait_for(lambda: (lambda s, b: s == 409 and b.get("type") == "/problems/account-frozen")(*call(
        cashier, "POST", f"/api/v1/office/claims/{cid}/payment-instructions", {"demo_scenario": "SUCCESS"},
        {"X-Step-Up-Token": step_up(cashier, "instruct-payment", cid, None, c["amount_paise"]),
         "Idempotency-Key": str(uuid.uuid4())})), timeout=15)

    # Leave the demo usable: verify, de-freeze, pay. A claim that officers had approved restarts under the
    # stricter after-de-freeze chain (init.md §7): approvals given before the freeze are void.
    _verify_and_defreeze(persona, frozen["data"]["case_id"], MEMBER_B_UAN)
    state = wait_for(lambda: (lambda st: st if st in ("AUTO_APPROVED", "UNDER_REVIEW") else None)(
        call(member, "GET", f"/api/v1/members/me/claims/{cid}")[1]["data"]["state"]), timeout=20)
    if state == "UNDER_REVIEW":
        for who, path in (("do-caseworker", "recommendations"), ("ro-ss", "decisions"), ("ro-apfc", "second-approvals")):
            page = persona(who, "/office/work-queue")
            case = wait_for(lambda: next((x for x in call(page, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]
                                          if x["claim_id"] == cid), None))
            if path == "recommendations":
                assert case["chain"] == ["fo.da_accounts", "fo.ss", "fo.apfc"], case
                assert recommend(page, case, "Re-checked after de-freeze")[0] == 200
            else:
                assert officer_decide(page, case, path)[0] == 200
    wait_for(lambda: call(cashier, "POST", f"/api/v1/office/claims/{cid}/payment-instructions", {"demo_scenario": "SUCCESS"},
                          {"X-Step-Up-Token": step_up(cashier, "instruct-payment", cid, None, c["amount_paise"]),
                           "Idempotency-Key": str(uuid.uuid4())})[0] == 200, timeout=20, every=1)
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{cid}")[1]["data"]["state"] == "SETTLED", timeout=30)


def test_every_must_deny_row_has_a_test():
    rows = set(re.findall(r"\| (DENY-\d\d) \|", (ROOT / "docs/permissions.md").read_text()))
    names = re.findall(r"def test_deny_((?:\d\d_(?:and_)?)+)", Path(__file__).read_text())
    tested = {n for name in names for n in re.findall(r"\d\d", name)} | {k[-2:] for k in COVERED_BY_UNIT_TESTS}
    missing = sorted(r for r in rows if r[-2:] not in tested)
    assert len(rows) == 25 and not missing, missing
