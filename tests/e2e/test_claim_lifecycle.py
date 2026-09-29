"""Phase 2, slice 5a on the running stack: a member uploads a document and withdraws a claim before a decision;
an approved claim gets its Claim Authorization Document from the accounts wing and is paid in a payment scroll by
the cash section; the dealing assistant looks up the member (360 view, purpose recorded), inoperative accounts
and the claim's audit trail."""
import base64
import uuid

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

PDF = base64.b64encode(b"%PDF-1.4 synthetic hospital estimate").decode()


def file_claim(member, account, amount):
    status, r = call(member, "POST", "/api/v1/members/me/claims", {"account_link_id": account, "claim_type": "ADVANCE_ILLNESS", "amount_paise": amount},
                     {"Idempotency-Key": str(uuid.uuid4())})
    if status == 409 and r.get("type") == "/problems/claim-already-open":   # left by an interrupted run: carry on with it
        left = call(member, "GET", f"/api/v1/members/me/claims/{r['claim_id']}")[1]["data"]
        if left["state"] != "AWAITING_CONFIRMATION":
            return left
        r = {"data": {**left, "confirmation": {"action": "confirm-claim", "resource_id": left["claim_id"], "resource_version": left["version"],
                                                "amount_paise": left["amount_paise"]}}}
        status = 201
    assert status == 201, r
    c = r["data"]
    conf = c["confirmation"]
    status, r = call(member, "POST", f"/api/v1/members/me/claims/{c['claim_id']}/confirmations", None,
                     {"X-Step-Up-Token": step_up(member, conf["action"], conf["resource_id"], conf["resource_version"], conf["amount_paise"])})
    assert status == 200, r
    return r["data"]


def test_member_uploads_a_document_and_withdraws_before_a_decision(persona):
    member = persona("member-a", "/member/claims")
    preview = call(member, "GET", "/api/v1/members/me/claims/eligibility-preview?formType=31")[1]["data"]
    assert preview["accounts"][0]["types"]
    c = file_claim(member, "AL-0001", 15000000)                        # ₹1,50,000: above the automatic limit, so reviewed
    assert c["state"] == "UNDER_REVIEW"
    status, doc = call(member, "POST", f"/api/v1/members/me/claims/{c['claim_id']}/documents",
                       {"filename": "estimate.pdf", "content_type": "application/pdf", "content_base64": PDF})
    assert status == 201 and len(doc["data"]["sha256"]) == 64, doc
    status, r = call(member, "POST", f"/api/v1/members/me/claims/{c['claim_id']}/cancellations", None,
                     {"X-Step-Up-Token": step_up(member, "cancel-claim", c["claim_id"])})
    assert status == 200 and r["data"]["state"] == "CANCELLED", r
    trail = call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}/audit-trail")[1]["data"]
    assert trail["events"][-1]["state"] == "CANCELLED"
    da = persona("do-caseworker", "/office/work-queue")
    wait_for(lambda: all(x["claim_id"] != c["claim_id"] for x in call(da, "GET", "/api/v1/office/work-queue")[1]["data"]["items"]), timeout=20)


def test_cad_then_payment_scroll_and_the_das_lookups(persona):
    member = persona("member-b", "/member/claims")
    c = file_claim(member, "AL-0002", 100000)                           # ₹1,000: settled automatically
    assert c["state"] == "AUTO_APPROVED"
    fa = persona("ro-fa-accounts", "/office/claim-tools")
    status, cad = wait_for(lambda: (lambda r: r if r[0] == 201 or r[1].get("type") == "/problems/cad-exists" else None)(call(
        fa, "POST", f"/api/v1/office/claims/{c['claim_id']}/cad", None,
        {"X-Step-Up-Token": step_up(fa, "generate-cad", c["claim_id"], None, 100000)})), timeout=30, every=2)
    if status == 409:                                                   # generated on an interrupted earlier run
        cad = call(fa, "GET", f"/api/v1/office/claims/{c['claim_id']}/cad")[1]
    assert cad["data"]["net_paise"] == 100000 and cad["data"]["static_data_version"]
    cashier = persona("ro-cashier", "/office/claim-tools")
    preview = call(cashier, "GET", "/api/v1/office/payment-scrolls/ready")[1]["data"]
    assert c["claim_id"] in [x["claim_id"] for x in preview["claims"]]
    status, scroll = call(cashier, "POST", "/api/v1/office/payment-scrolls", {"demo_scenario": "SUCCESS"},
                          {"X-Step-Up-Token": step_up(cashier, "generate-scroll", "RO-DEMO-01", None, preview["total_paise"])})
    assert status == 201, scroll
    wait_for(lambda: call(member, "GET", f"/api/v1/members/me/claims/{c['claim_id']}")[1]["data"]["state"] == "SETTLED", timeout=30)
    status, rec = call(cashier, "POST", f"/api/v1/office/payment-scrolls/{scroll['data']['scroll_id']}/return-reconciliations", None,
                       {"X-Step-Up-Token": step_up(cashier, "reconcile-scroll", scroll["data"]["scroll_id"], None, preview["total_paise"])})
    assert status == 200 and c["claim_id"] in rec["data"]["paid"], rec

    da = persona("do-caseworker", "/office/claim-tools")
    status, m = call(da, "GET", "/api/v1/office/members/100000000002?purpose=Checking%20a%20settled%20advance")
    assert status == 200 and m["data"]["viewed_for"] == "Checking a settled advance"
    assert call(da, "GET", "/api/v1/office/members/100000000002")[0] in (400, 422)                  # no purpose, no view
    assert call(da, "GET", "/api/v1/office/accounts/inoperative")[0] == 200
    trail = call(da, "GET", f"/api/v1/office/claims/{c['claim_id']}/audit-trail")[1]["data"]
    assert trail["cad"]["cad_id"] == cad["data"]["cad_id"] and trail["state"] == "SETTLED"
    SHOTS.mkdir(exist_ok=True)
    fa.goto(f"{WEB}/office/claim-tools")
    fa.get_by_label("Claim ID").fill(c["claim_id"])
    fa.get_by_role("button", name="Generate or view CAD").click()
    fa.get_by_text("A CAD already exists for this claim.").wait_for()
    fa.screenshot(path=str(SHOTS / "p2-cad.png"), full_page=True)
