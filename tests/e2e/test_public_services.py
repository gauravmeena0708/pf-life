"""Phase 2, slice 8d on the running stack: a grievance filed without a login and its status; a member's reminder
and closing feedback; a grievance transferred between offices; claim status without a login; circulars published
by HO and read by anyone; an establishment's e-Report Card; the approved interest rate recorded by HO F&A becoming a
draft rule set; a surrendered trust's past accumulations ingested by the exemption cell. Repeatable."""
import re
import secrets
from datetime import UTC, datetime

from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.test_journey_c_grievance import grievance_case
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def ask(page, path, body):
    """A public POST with the gateway's one-use demo question answered."""
    challenge = call(page, "GET", "/api/v1/public/demo-challenges")[1]["data"]
    a, b = map(int, re.findall(r"\d+", challenge["prompt"])[:2])
    return call(page, "POST", path, {**body, "challenge_id": challenge["challenge_id"], "answer": a + b})


def test_grievance_without_login_and_its_status(persona):
    visitor = persona("member-a", "/public")                           # any browser: these need no login
    mobile = f"9{secrets.randbelow(10**9):09d}"
    body = {"name": "Pensioner Demo", "mobile": mobile, "otp": "123456", "complainant_type": "PENSIONER", "category": "OTHER",
            "subject": "Pension credited late", "description": "My pension for August was credited on the 12th instead of the 1st."}
    assert call(visitor, "POST", "/api/v1/public/grievances", body)[0] in (400, 403)          # the demo question first
    status, r = ask(visitor, "/api/v1/public/grievances", {**body, "otp": "000000"})
    assert status == 422, r
    status, r = ask(visitor, "/api/v1/public/grievances", body)
    assert status == 201 and r["data"]["registration_no"].startswith("GRV-") and r["data"]["state"] == "ROUTED", r
    reg = r["data"]["registration_no"]
    status, s = ask(visitor, "/api/v1/public/grievances/status-lookups", {"registration_no": reg, "mobile": mobile, "otp": "123456"})
    assert status == 200 and s["data"]["state"] == "ROUTED" and "credited late" not in str(s), s
    status, _ = ask(visitor, "/api/v1/public/grievances/status-lookups", {"registration_no": reg, "mobile": "9000000001", "otp": "123456"})
    assert status == 404
    pro = persona("ro-pro", "/office/work-queue")
    wait_for(lambda: grievance_case(pro, reg), timeout=30)                  # the office has it like any other


def test_reminder_feedback_and_office_transfer(persona):
    member = persona("member-a", "/member/grievances")
    status, g = call(member, "POST", "/api/v1/members/me/grievances", {"category": "PASSBOOK", "subject": "Passbook not updated",
                                                                       "description": "The August contribution is not in my passbook yet."})
    assert status == 201, g
    gid = g["data"]["grievance_id"]
    status, r = call(member, "POST", f"/api/v1/grievances/{gid}/reminders", {"note": "Please look into it"})
    assert status == 201 and r["data"]["reminders"] == 1, r
    assert call(member, "POST", f"/api/v1/grievances/{gid}/reminders", {})[0] == 429
    pro = persona("ro-pro", "/office/work-queue")
    case = wait_for(lambda: grievance_case(pro, gid), timeout=30)
    status, r = call(pro, "POST", f"/api/v1/grievances/{gid}/messages", {"body": "The passbook updates overnight; checking."})
    assert status == 201 and r["data"]["state"] == "IN_PROGRESS", r
    status, r = call(pro, "POST", f"/api/v1/grievances/{gid}/resolution", {"resolution": "The passbook was updated on the next run."},
                     {"X-Step-Up-Token": step_up(pro, "resolve-grievance", gid, r["data"]["version"])})
    assert status == 200 and r["data"]["state"] == "RESOLVED", r
    status, r = call(member, "POST", f"/api/v1/grievances/{gid}/feedback", {"rating": 5, "satisfied": True, "comment": "Thank you"})
    assert status == 201 and r["data"]["state"] == "CLOSED", r
    assert case

    status, g = call(member, "POST", "/api/v1/members/me/grievances", {"category": "EMPLOYER", "subject": "Employer in another region",
                                                                       "description": "My earlier employer is in the other office's area."})
    gid = g["data"]["grievance_id"]
    wait_for(lambda: grievance_case(pro, gid), timeout=30)
    call(pro, "POST", f"/api/v1/grievances/{gid}/messages", {"body": "This belongs to the other office."})
    status, r = call(pro, "POST", f"/api/v1/grievances/{gid}/office-transfers", {"to_office_id": "RO-DEMO-02",
                                                                                "reason": "The establishment is in RO-DEMO-02's area"})
    assert status == 200 and r["data"]["office_id"] == "RO-DEMO-02", r
    assert call(pro, "GET", f"/api/v1/grievances/{gid}")[0] == 404
    wait_for(lambda: grievance_case(pro, gid) is None, timeout=30)
    assert call(member, "GET", f"/api/v1/grievances/{gid}")[1]["data"]["office_id"] == "RO-DEMO-02"


def test_claim_status_circulars_and_e_report_card(persona):
    member = persona("member-a", "/public")
    claims = [c for c in call(member, "GET", "/api/v1/members/me/claims")[1]["data"] if c["state"] != "AWAITING_CONFIRMATION"]
    if claims:
        status, r = ask(member, "/api/v1/public/claims/status-lookups", {"claim_id": claims[0]["claim_id"], "uan": "100000000001", "otp": "123456"})
        assert status == 200 and r["data"]["state"] == claims[0]["state"] and "amount_paise" not in r["data"], r
        assert ask(member, "/api/v1/public/claims/status-lookups", {"claim_id": claims[0]["claim_id"], "uan": "100000000002", "otp": "123456"})[0] == 404

    pr = persona("ho-publicity", "/ho/circulars")
    number = f"DEMO/E2E/{secrets.token_hex(3).upper()}"
    today = datetime.now(UTC).date().isoformat()
    body = {"number": number, "title": "Test circular (synthetic)", "category": "GENERAL", "issued_on": today,
            "summary": "A synthetic circular published by the end-to-end test.", "body": "SYNTHETIC. First version of the text."}
    status, c = call(pr, "POST", "/api/v1/ho/circulars", body)
    assert status == 201 and c["data"]["version"] == 1, c
    status, c = call(pr, "POST", "/api/v1/ho/circulars", {**body, "body": "SYNTHETIC. Second version of the text."})
    assert status == 201 and c["data"]["version"] == 2, c
    listed = call(member, "GET", f"/api/v1/public/circulars?number={number}")[1]["data"]["circulars"]
    assert [(x["version"], x["state"]) for x in listed] == [(2, "CURRENT"), (1, "SUPERSEDED")]
    assert any(x["number"] == "DEMO/PENSION/2026/02" for x in call(member, "GET", "/api/v1/public/circulars?category=PENSION")[1]["data"]["circulars"])

    card = call(member, "GET", "/api/v1/public/establishments/EST-DEMO-0001/e-report-card")
    assert card[0] == 200 and len(card[1]["data"]["months"]) <= 12 and "counts" in card[1]["data"], card
    assert call(member, "GET", "/api/v1/public/establishments/EST-NOPE-9999/e-report-card")[0] == 404


def test_interest_rate_record_and_trust_ingestion(persona):
    finance = persona("ho-finance", "/finance/interest")
    fy, rate = "2026-27", 815 + secrets.randbelow(10)
    body = {"rate_bp": rate, "cbt_recommended_on": "2026-02-10", "ministry_concurrence_ref": f"DEMO-MOL-{secrets.token_hex(2).upper()}",
            "ministry_concurrence_on": "2026-05-20", "note": "Synthetic record for the demonstration"}
    status, r = call(finance, "PUT", f"/api/v1/ho/config/interest-rates/{fy}", body,
                     {"X-Step-Up-Token": step_up(finance, "record-interest-rate", fy, None, rate)})
    assert status == 200 and r["data"]["rate_bp"] == rate, r
    declaration = r["data"]["declaration_id"]
    drafter = persona("ho-policy", "/policy")
    draft = wait_for(lambda: next((x for x in call(drafter, "GET", "/api/v1/ho/config/rule-sets")[1]["data"]["items"]
                                   if declaration in (x.get("change_note") or "")), None), timeout=30)
    assert draft["status"] == "DRAFT", draft
    doc = call(drafter, "GET", f"/api/v1/ho/config/rule-sets/{draft['version_id']}")[1]["data"]
    assert doc["document"]["interest"]["rates_bp"][fy] == rate

    cell = persona("ro-exemption", "/office/exempted")
    content = "uan,account_link_id,employee_rupees,employer_rupees,pension_rupees\n100000000908,AL-0910,40000,30000,5000\n100000000909,AL-0912,25000,20000,0\n"
    total = (40000 + 30000 + 5000 + 25000 + 20000) * 100
    reference = f"TRUST-NEFT-{secrets.token_hex(4).upper()}"
    bad = call(cell, "POST", "/api/v1/office/exempted/EST-DEMO-0003/past-accumulation-ingestions",
               {"transfer_reference": reference, "content": content + "100000000001,AL-0001,100,0,0\n"},
               {"X-Step-Up-Token": step_up(cell, "ingest-past-accumulation", "EST-DEMO-0003", None, total + 10000)})
    assert bad[0] == 422 and "not a member ID" in bad[1]["detail"], bad
    status, r = call(cell, "POST", "/api/v1/office/exempted/EST-DEMO-0003/past-accumulation-ingestions",
                     {"transfer_reference": reference, "content": content},
                     {"X-Step-Up-Token": step_up(cell, "ingest-past-accumulation", "EST-DEMO-0003", None, total)})
    assert status == 201 and r["data"]["members"] == 2 and r["data"]["total_paise"] == total and all(x["journal_id"] for x in r["data"]["lines"]), r
    again = call(cell, "POST", "/api/v1/office/exempted/EST-DEMO-0003/past-accumulation-ingestions",
                 {"transfer_reference": reference, "content": content},
                 {"X-Step-Up-Token": step_up(cell, "ingest-past-accumulation", "EST-DEMO-0003", None, total)})
    assert again[0] == 409
