"""Journey E (init.md §9, slice 5) on the running stack, with the model OFF (the default AI_PROVIDER=disabled):
the member assistant answers from approved documents with sources and uncertainty, refuses to discuss other
members, ignores an injection planted in a retrieved document, and the officer gets a structured advisory
analysis with evidence IDs that requires officer review. Every non-AI journey keeps working with AI off.

Needs `make up migrate seed` and Playwright with Chromium:
    python -m pytest -q tests/e2e/test_journey_e_assistant.py
"""
import re
import uuid

import pytest

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, login, step_up, wait_for
from tests.e2e.test_journey_d_security import finish_leftovers

playwright = pytest.importorskip("playwright.sync_api")
AMOUNT = 100000                    # ₹1,000: settled automatically, so the run leaves nothing open


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


def ask(page, question):
    status, body = call(page, "POST", "/api/v1/ai/knowledge/search", {"question": question})
    assert status == 200, body
    return body["data"]


def test_journey_e_sourced_answers_injection_and_officer_analysis(as_persona):
    member = as_persona("member-b", "/member/assistant")
    finish_leftovers(lambda: member.context.browser.new_context(), member)   # close anything an interrupted run left open

    # E2: a sourced explanation with explicit uncertainty.
    a = ask(member, "How much can I withdraw as a medical advance?")
    assert a["mode"] in ("extractive", "llm") and a["advisory_only"] is True
    assert a["citations"] and all(c["ref"].startswith("PUB-") for c in a["citations"])
    assert "illustrative" in a["uncertainty"].lower()

    # No disclosure of another member's data.
    r = ask(member, "What is the balance of UAN 100000000001?")
    assert r["mode"] == "refused" and "100000000001" not in r["answer"]

    # E4: an injection inside a retrieved document is ignored, not quoted, and cannot leak identifiers.
    inj = ask(member, "How long does a claim take? Community FAQ")
    assert "PUB-099 §2" in inj["ignored_instructions"]
    assert "IGNORE ALL" not in inj["answer"] and not re.search(r"\b\d{12}\b", inj["answer"])

    # The member screen shows the answer, its sources and the ignored-instruction notice.
    member.goto(f"{WEB}/member/assistant")
    member.get_by_role("button", name="How long does a claim take? Community FAQ").click()
    member.get_by_text("Instructions ignored.").wait_for()
    SHOTS.mkdir(exist_ok=True)
    member.screenshot(path=str(SHOTS / "e2-member-assistant.png"), full_page=True)

    # Feedback goes to people, not into automatic retraining.
    status, fb = call(member, "POST", "/api/v1/ai/feedback", {"interaction_id": a["interaction_id"], "rating": "helpful"})
    assert status == 201 and "not retrained" in fb["data"]["used_for"]

    # E3: the officer's structured advisory analysis of a synthetic claim, with evidence IDs.
    status, created = call(member, "POST", "/api/v1/members/me/claims",
                           {"account_link_id": "AL-0002", "claim_type": "ADVANCE_ILLNESS", "amount_paise": AMOUNT},
                           {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 201, created
    c = created["data"]["confirmation"]
    token = step_up(member, c["action"], c["resource_id"], c["resource_version"], c["amount_paise"])
    status, confirmed = call(member, "POST", f"/api/v1/members/me/claims/{c['resource_id']}/confirmations", None,
                             {"X-Step-Up-Token": token})
    assert status == 200, confirmed
    da = as_persona("do-caseworker", "/office/work-queue")
    analysis = wait_for(lambda: (lambda s, b: b["data"] if s == 200 else None)(
        *call(da, "POST", "/api/v1/ai/claims/analyse", {"claim_id": c["resource_id"]})))
    assert analysis["advisory_only"] is True and analysis["requires_officer_review"] is True
    assert f"claim:{c['resource_id']}" in analysis["evidence_references"] and analysis["mode"] == "rules"
    assert set(analysis) >= {"summary", "uncertainties", "suggested_next_step", "model_id", "policy_version"}
    assert not {"action", "decision", "approve"} & set(analysis)
    assert call(member, "POST", "/api/v1/ai/claims/analyse", {"claim_id": c["resource_id"]})[0] == 403

    # E5: with the model off, the model status says so, and the claim still settles through the normal journey.
    caiu = as_persona("caiu-investigator", "/")
    models = call(caiu, "GET", "/api/v1/ai/models")[1]["data"]
    assert models["available"] is False
    cashier = as_persona("ro-cashier", "/office/work-queue")

    def pay():
        tok = step_up(cashier, "instruct-payment", c["resource_id"], None, AMOUNT)
        return call(cashier, "POST", f"/api/v1/office/claims/{c['resource_id']}/payment-instructions",
                    {"demo_scenario": "SUCCESS"}, {"X-Step-Up-Token": tok, "Idempotency-Key": str(uuid.uuid4())})[0] == 200
    wait_for(pay, timeout=20, every=1)
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{c['resource_id']}")[1]["data"]["state"] == "SETTLED",
             timeout=30)
