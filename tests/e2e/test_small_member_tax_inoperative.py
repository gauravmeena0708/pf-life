"""Phase 2, slice 12a on the running stack: Form 16A and the quarterly TDS statement; UAN allotment at a CSC (mock
face authentication) and UAN activation (demo OTP); an inoperative account (MOHAN DEMO, left in 2019) found through
the public search (demo CAPTCHA, then an OTP before the balance), confirmed by two co-workers and reactivated by the
AO. Repeatable: a fresh Aadhaar for each allotment; once the account is reactivated a later run checks it stays so."""
import random
import re
from datetime import date

from tests.e2e.test_journey_a_ecr import call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

INOPERATIVE = "AL-0913"


def fy(day: date) -> str:
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def test_form_16a_and_the_quarterly_tds_statement(persona):
    member = persona("member-a", "/member/claims")
    status, r = call(member, "GET", f"/api/v1/members/me/tax/form-16a?financialYear={fy(date.today())}")
    assert status == 200 and r["data"]["section"] == "192A" and len(r["data"]["quarters"]) == 4, r
    assert call(member, "GET", "/api/v1/members/me/tax/form-16a?financialYear=2026")[0] == 422
    da = persona("do-caseworker", "/office/claim-tools")
    status, r = call(da, "POST", "/api/v1/office/tds/computations", {"financial_year": "2026-27", "quarter": "Q1"})
    assert (status in (200, 201) and r["data"]["acknowledgement"].startswith("26Q-ACK-")) or \
        (status == 409 and r["type"] == "/problems/already-filed"), r                 # filed by an earlier run
    assert call(da, "POST", "/api/v1/office/tds/computations", {"financial_year": "2030-31", "quarter": "Q4"})[0] == 422
    assert call(member, "POST", "/api/v1/office/tds/computations", {"financial_year": "2026-27", "quarter": "Q1"})[0] == 403


def test_uan_allotment_at_a_csc_and_activation(persona):
    csc = persona("csc-operator", "/csc")
    aadhaar = "9" + "".join(random.choice("0123456789") for _ in range(11))
    body = {"aadhaar": aadhaar, "name": "Synthetic Applicant", "date_of_birth": "1999-01-01", "gender": "FEMALE",
            "mobile": "9876500099", "face_auth_token": "MOCK-FACE-MATCH"}
    assert call(csc, "POST", "/api/v1/members/uan-allotments", {**body, "face_auth_token": "NO-MATCH"})[0] == 422
    status, r = call(csc, "POST", "/api/v1/members/uan-allotments", body)
    assert status in (200, 201) and re.fullmatch(r"\d{12}", r["data"]["uan"]) and aadhaar not in str(r), r
    status, again = call(csc, "POST", "/api/v1/members/uan-allotments", body)
    assert status == 409 and again["type"] == "/problems/uan-exists" and aadhaar not in str(again)
    member = persona("member-a", "/member/security")
    assert call(member, "POST", "/api/v1/members/uan-allotments", body)[0] == 409       # a member already has a UAN
    status, r = call(member, "POST", "/api/v1/members/uan-activations", {"uan": "100000000001", "otp": "123456"})
    assert status in (200, 201) or (status == 409 and r["type"] == "/problems/already-active"), r
    assert call(member, "POST", "/api/v1/members/uan-activations", {"uan": "100000000002", "otp": "123456"})[0] == 403


def test_inoperative_account_found_verified_and_reactivated(persona):
    da = persona("do-caseworker", "/office/claim-tools")
    listed = call(da, "GET", "/api/v1/office/accounts/inoperative?include_reactivated=true")[1]["data"]["accounts"]
    mohan = next(a for a in listed if a["account_link_id"] == INOPERATIVE)
    if mohan.get("reactivated"):                                                     # an earlier run reactivated it
        assert INOPERATIVE not in [a["account_link_id"] for a in call(da, "GET", "/api/v1/office/accounts/inoperative")[1]["data"]["accounts"]]
        return

    visitor = persona("member-a", "/public")                                         # any browser; the search needs no login

    def ask(body):
        challenge = call(visitor, "GET", "/api/v1/public/demo-challenges")[1]["data"]
        a, b = map(int, re.findall(r"\d+", challenge["prompt"])[:2])
        return call(visitor, "POST", "/api/v1/public/inoperative-accounts/searches", {**body, "challenge_id": challenge["challenge_id"], "answer": a + b})
    status, r = ask({"name": "mohan demo", "date_of_birth": "1970-02-14", "establishment_query": "textiles"})
    assert status == 200 and len(r["data"]["matches"]) == 1 and "balance" not in str(r["data"]["matches"]), r
    ref, otp = r["data"]["matches"][0]["search_ref"], r["data"]["demo"]["otp"]
    assert ask({"search_ref": ref, "otp": "000000" if otp != "000000" else "111111"})[0] == 422
    status, r = ask({"search_ref": ref, "otp": otp})
    assert status == 200 and r["data"]["balance_paise"] == mohan["balance_paise"], r

    ao = persona("ro-ao", "/office/claim-tools")

    def reactivate():
        return call(ao, "POST", f"/api/v1/office/accounts/{INOPERATIVE}/reactivations", {"decision": "REACTIVATE", "note": "Identity confirmed by co-workers"},
                    {"X-Step-Up-Token": step_up(ao, "reactivate-account", INOPERATIVE, None, mohan["balance_paise"])})
    if not mohan.get("verified"):
        status, r = reactivate()
        assert status == 409 and r["type"] == "/problems/not-verified", r
        status, r = call(da, "POST", f"/api/v1/office/accounts/{INOPERATIVE}/crowdsource-verifications",
                         {"co_worker_uans": ["100000000004"], "note": "One co-worker only"})
        assert status == 422, r
        status, r = call(da, "POST", f"/api/v1/office/accounts/{INOPERATIVE}/crowdsource-verifications",
                         {"co_worker_uans": ["100000000004", "100000000906"], "note": "Both worked with him at the mill"})
        assert status in (200, 201), r
    from tests.e2e.test_journey_a_ecr import wait_for
    wait_for(lambda: next(a for a in call(da, "GET", "/api/v1/office/accounts/inoperative")[1]["data"]["accounts"]
                          if a["account_link_id"] == INOPERATIVE).get("verified"), timeout=30)
    status, r = reactivate()
    assert status == 200, r
    assert INOPERATIVE not in [a["account_link_id"] for a in call(da, "GET", "/api/v1/office/accounts/inoperative")[1]["data"]["accounts"]]
