"""Journey A (init.md §9, slice 2) on the running stack: an employer verifies, grants roles, files a monthly
return (ECR), approves and submits it, pays the challan through the mock bank, and the member sees the credit.

Every call goes browser → gateway → service with a real Keycloak session, CSRF, step-up and idempotency.
Needs `make up migrate seed` and Playwright with Chromium:
    python -m pytest -q tests/e2e/test_journey_a_ecr.py
"""
import json
import random
import re
import time
import uuid
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

WEB = "http://localhost:5173"
PASSWORD = "Demo@2026!"
SEED = json.load(open(Path(__file__).resolve().parents[2] / "scripts" / "seed" / "synthetic.json"))
EST = SEED["establishment"]
SHOTS = Path(__file__).resolve().parent / "screenshots"


def login(page, persona: str, return_to: str = "/") -> None:
    page.goto(f"{WEB}/auth/login?persona={persona}&return_to={return_to}")
    page.wait_for_url(re.compile(r"localhost:8080/realms/epfo-demo/"))
    page.locator("#password").wait_for()
    if not page.locator("#username").count() and page.locator("#reset-login").count():
        page.click("#reset-login")            # a shared browser: Keycloak offers the previous user; start over
        page.locator("#username").wait_for()
    if page.locator("#username").input_value() != persona:
        page.fill("#username", persona)
    page.fill("#password", PASSWORD)
    page.click("#kc-login")
    page.wait_for_url(f"{WEB}{return_to}")


def call(page, method: str, path: str, body=None, headers=None) -> tuple[int, dict]:
    return tuple(page.evaluate(
        """async ([method, path, body, extra]) => {
            const csrf = document.cookie.split('; ').find(c => c.startsWith('epfo-csrf='))?.split('=')[1];
            const headers = {Accept: 'application/json', ...extra};
            if (method !== 'GET' && csrf) headers['X-CSRF-Token'] = csrf;
            if (body !== null) headers['Content-Type'] = 'application/json';
            const r = await fetch(path, {method, headers, credentials: 'include',
                                         body: body === null ? undefined : JSON.stringify(body)});
            const text = await r.text();
            return [r.status, text ? JSON.parse(text) : {}];
        }""",
        [method, path, body, headers or {}],
    ))


def step_up(page, action, resource_id, resource_version=None, amount_paise=None) -> str:
    status, ch = call(page, "POST", "/api/v1/security/step-up-challenges", {
        "action": action, "resource_id": resource_id, "resource_version": resource_version,
        "amount_paise": amount_paise, "summary": f"e2e {action}"})
    assert status in (200, 201), ch
    c = ch["data"]
    status, ok = call(page, "POST", f"/api/v1/security/step-up-challenges/{c['challenge_id']}/verifications",
                      {"otp": c["demo_otp"]})
    assert status == 200, ok
    return ok["data"]["step_up_token"]


def ecr_line(uan, name, wages):
    ee, eps = round(wages * 0.12), round(min(wages, 15000) * 0.0833)
    return "#~#".join(map(str, [uan, name, wages, wages, min(wages, 15000), min(wages, 15000), ee, eps, ee - eps, 0, 0]))


def wait_for(fn, timeout=20.0, every=0.5):
    end = time.time() + timeout
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(every)
    raise AssertionError("condition not met in time")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def as_persona(browser):
    contexts = []

    def make(persona, return_to="/"):
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        contexts.append(ctx)
        page = ctx.new_page()
        login(page, persona, return_to)
        return page
    yield make
    for c in contexts:
        c.close()


def ensure_verified_and_granted(owner):
    status, me = call(owner, "GET", "/api/v1/employers/me")
    assert status == 200, me
    if me["data"]["status"] != "VERIFIED":
        status, v = call(owner, "POST", f"/api/v1/employers/registration-requests/{me['data']['registration_request_id']}/verification-evidence",
                         {"pan": EST["pan"], "gstin": EST["gstin"]})
        assert status == 200 and v["data"]["state"] == "VERIFIED", v
    active = lambda kind: {g["username"] for g in call(owner, "GET", f"/api/v1/employers/me/{kind}")[1]["data"] if g["status"] == "ACTIVE"}
    if "emp-preparer" not in active("operators"):
        token = step_up(owner, "invite-operator", EST["establishment_id"])
        status, r = call(owner, "POST", "/api/v1/employers/me/operators/invitations",
                         {"username": "emp-preparer", "grants": ["ecr.prepare"]}, {"X-Step-Up-Token": token})
        assert status == 201, r
    if "emp-signatory" not in active("signatories"):
        token = step_up(owner, "authorise-signatory", EST["establishment_id"])
        status, r = call(owner, "POST", "/api/v1/employers/me/signatories/authorisations",
                         {"username": "emp-signatory", "grants": ["ecr.approve", "ecr.submit", "payment.initiate"]},
                         {"X-Step-Up-Token": token})
        assert status == 201, r


def test_journey_a_file_pay_and_member_sees_credit(as_persona):
    SHOTS.mkdir(exist_ok=True)
    owner = as_persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    owner.goto(f"{WEB}/employer")
    owner.get_by_role("heading", level=1).wait_for()
    owner.screenshot(path=str(SHOTS / "a1-employer-workspace.png"), full_page=True)

    # A3/A4: the operator uploads; the file is validated on arrival. A random past month keeps reruns independent.
    preparer = as_persona("emp-preparer", "/employer/ecr")
    month = f"{random.randint(2001, 2019)}-{random.randint(1, 12):02d}"
    members = SEED["members"][:3]
    content = "\n".join(ecr_line(m["uan"], m["name"], w) for m, w in zip(members, (15000, 22000, 18000)))
    status, created = call(preparer, "POST", "/api/v1/employers/me/ecr-filings",
                           {"wage_month": month, "format": "ECR_TXT", "content": content})
    assert status == 201, created
    filing, report = created["data"]["filing"], created["data"]["validation_report"]
    assert filing["state"] == "VALIDATED", report["issues"]
    total = report["summary"]["totals_paise"]["TOTAL"]
    preparer.goto(f"{WEB}/employer/ecr")
    preparer.get_by_role("heading", level=1).wait_for()
    preparer.screenshot(path=str(SHOTS / "a3-ecr-upload.png"), full_page=True)

    # Separation of duties: the operator has no approval grant.
    status, denied = call(preparer, "POST", f"/api/v1/employers/me/ecr-filings/{filing['filing_id']}/approvals", {"decision": "APPROVE"})
    assert status == 403, denied

    # A5: the signatory approves and submits, each bound by step-up to this filing, version and amount.
    signatory = as_persona("emp-signatory", "/employer/ecr")
    fid, ver = filing["filing_id"], filing["version"]
    token = step_up(signatory, "approve-ecr", fid, ver, total)
    status, r = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{fid}/approvals", {"decision": "APPROVE"}, {"X-Step-Up-Token": token})
    assert status == 200 and r["data"]["state"] == "APPROVED", r
    key = str(uuid.uuid4())
    token = step_up(signatory, "submit-ecr", fid, ver, total)
    status, sub = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{fid}/submissions", None,
                       {"X-Step-Up-Token": token, "Idempotency-Key": key, "If-Match": str(ver)})
    assert status == 201, sub
    trrn = sub["data"]["trrn"]
    assert sub["data"]["total_paise"] == total

    # A network retry with the same Idempotency-Key returns the same challan, never a second one.
    token = step_up(signatory, "submit-ecr", fid, ver, total)
    status, again = call(signatory, "POST", f"/api/v1/employers/me/ecr-filings/{fid}/submissions", None,
                         {"X-Step-Up-Token": token, "Idempotency-Key": key, "If-Match": str(ver)})
    assert status == 201 and again["data"]["trrn"] == trrn

    # Before payment the member sees the return as filed but not yet credited.
    member = as_persona("member-a", "/member/passbook")
    pending = wait_for(lambda: [p for p in call(member, "GET", "/api/v1/members/me/passbook")[1]["data"]["pending"]
                                if p["wage_month"] == month])
    assert "awaiting payment" in pending[0]["message"]
    member.goto(f"{WEB}/member/passbook")
    member.get_by_role("heading", level=1).wait_for()
    member.screenshot(path=str(SHOTS / "a7-passbook-pending.png"), full_page=True)

    # A6: pay the challan through the mock bank (payment-simulator learns the challan from ECRSubmitted.v1).
    def pay():
        token = step_up(signatory, "pay-challan", trrn, None, total)
        status, body = call(signatory, "POST", f"/api/v1/employers/me/challans/{trrn}/payment-intents",
                            {"channel": "NET_BANKING"}, {"X-Step-Up-Token": token, "Idempotency-Key": str(uuid.uuid4())})
        return body if status == 202 else None
    paid = wait_for(pay, timeout=15, every=1)
    assert paid["data"]["mock"] is True
    wait_for(lambda: call(signatory, "GET", f"/api/v1/employers/me/challans/{trrn}")[1]["data"]["status"] == "PAID", timeout=30)
    status, receipt = call(signatory, "GET", f"/api/v1/employers/me/challans/{trrn}/receipt")
    assert status == 200 and receipt["data"]["total_paise"] == total

    # A7: the posted contribution appears in the member passbook with the employee and employer shares.
    def credited():
        data = call(member, "GET", "/api/v1/members/me/passbook")[1]["data"]
        return [e for a in data["accounts"] for e in a["entries"] if e["wage_month"] == month]
    entry = wait_for(credited, timeout=30)[0]
    assert entry["trrn"] == trrn and entry["employee_share_paise"] == 180000  # 12 % of ₹15,000
    member.goto(f"{WEB}/member/passbook")
    member.get_by_text(trrn).first.wait_for()
    member.screenshot(path=str(SHOTS / "a7-passbook-credited.png"), full_page=True)


def test_revoked_operator_is_denied_within_five_seconds(as_persona):
    owner = as_persona("emp-owner", "/employer")
    ensure_verified_and_granted(owner)
    preparer = as_persona("emp-preparer", "/employer")
    assert call(preparer, "GET", "/api/v1/employers/me/ecr-filings")[0] == 200
    grant = next(g for g in call(owner, "GET", "/api/v1/employers/me/operators")[1]["data"]
                 if g["username"] == "emp-preparer" and g["status"] == "ACTIVE")
    token = step_up(owner, "revoke-operator", grant["grant_id"])
    status, r = call(owner, "POST", f"/api/v1/employers/me/operators/{grant['grant_id']}/revocations",
                     {"reason": "e2e revocation"}, {"X-Step-Up-Token": token})
    assert status == 200, r
    revoked_at = time.time()
    status, _ = wait_for(lambda: (lambda s: s if s[0] in (401, 403) else None)(
        call(preparer, "GET", "/api/v1/employers/me/ecr-filings")), timeout=5, every=0.25)
    assert time.time() - revoked_at <= 5
    ensure_verified_and_granted(owner)  # leave the demo usable


def test_shell_has_account_menu_in_header_not_in_page(as_persona):
    page = as_persona("member-a", "/")
    assert page.locator("header.topbar details.account-menu").count() == 1
    assert page.locator("main details.account-menu, main #persona-select").count() == 0
    page.screenshot(path=str(SHOTS / "home.png"), full_page=True)
    page.locator("details.account-menu summary").click()
    page.screenshot(path=str(SHOTS / "home-account-menu.png"))
