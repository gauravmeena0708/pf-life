"""Phase 2, slice 3 on the running stack: pension office and pensioner self-service.

The APFC (Pension) suspends a pension whose life certificate lapsed (PPO-DEMO-0002); the DA (Pension) records a
physical life certificate as an updation activity and the APFC settles it, which resumes the pension. The
pensioner submits a Digital Life Certificate (mock Jeevan Pramaan), sees the PPO and a slip, asks to change the
bank account (settled by the APFC) and makes a declaration. The public pension enquiries need the demo CAPTCHA.
On a rerun (certificate already renewed) the office exercises a DLC revalidation instead."""
import re
import secrets

from tests.e2e.test_journey_a_ecr import SHOTS, WEB, call, step_up
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def settle(apfc, activity_id, note="Checked by the APFC (Pension)"):
    status, r = call(apfc, "POST", f"/api/v1/office/pensions/updation-activities/{activity_id}/decisions", {"decision": "SETTLE", "note": note},
                     {"X-Step-Up-Token": step_up(apfc, "decide-pension-updation", activity_id)})
    assert status == 200 and r["data"]["status"] == "SETTLED", r
    return r["data"]


def initiate(da, ppo, activity, reason, **details):
    status, r = call(da, "POST", f"/api/v1/office/pensions/{ppo}/updation-activities",
                     {"activity": activity, "mode": "PHYSICAL", "reason": reason, "details": details},
                     {"X-Step-Up-Token": step_up(da, "initiate-pension-updation", ppo)})
    assert status == 201, r
    return r["data"]


def test_lapsed_certificate_suspension_and_resumption_through_the_office(persona):
    apfc, da = persona("ro-pension", "/office/pensions"), persona("ro-da-pension", "/office/pensions")
    assert call(da, "GET", "/api/v1/office/pensions/life-certificates/overdue")[0] == 200     # the DA sees the list too
    overdue = call(apfc, "GET", "/api/v1/office/pensions/life-certificates/overdue")[1]["data"]
    row = next((o for o in overdue if o["ppo_id"] == "PPO-DEMO-0002"), None)
    if row:                                                          # first run: the certificate lapsed on 31 August
        if row["status"] == "IN_PAYMENT":
            status, r = call(apfc, "POST", "/api/v1/office/pensions/PPO-DEMO-0002/suspensions", {"reason": "No life certificate since 31 August"},
                             {"X-Step-Up-Token": step_up(apfc, "suspend-pension", "PPO-DEMO-0002")})
            assert status == 200 and r["data"]["status"] == "SUSPENDED", r
        assert call(apfc, "POST", "/api/v1/office/pensions/PPO-DEMO-0002/resumptions", {"reason": "Try to resume without a certificate"},
                    {"X-Step-Up-Token": step_up(apfc, "resume-pension", "PPO-DEMO-0002")})[1]["type"] == "/problems/life-certificate-lapsed"
        activity = initiate(da, "PPO-DEMO-0002", "PHYSICAL_LC", "Life certificate given at the PRO counter")
    else:                                                            # rerun: revalidate the certificate instead
        activity = initiate(da, "PPO-DEMO-0002", "DLC_REVALIDATION", "Annual revalidation from the office")
    status, r = call(da, "POST", f"/api/v1/office/pensions/updation-activities/{activity['activity_id']}/decisions",
                     {"decision": "SETTLE", "note": "The DA cannot settle"})
    assert status == 403                                                                   # maker is not checker
    done = settle(apfc, activity["activity_id"])
    assert "valid till" in done["decision_note"]
    enquiry = call(da, "GET", "/api/v1/office/pensions/enquiries?ppo=PPO-DEMO-0002")[1]["data"]
    assert enquiry["ppo_details"]["status"] == "IN_PAYMENT" and enquiry["ppo_details"]["life_certificate"]["state"] == "VALID"
    tracker = call(da, "GET", "/api/v1/office/pensions/updation-activities?status=SETTLED")[1]["data"]
    assert activity["activity_id"] in [t["activity_id"] for t in tracker]
    SHOTS.mkdir(exist_ok=True)
    da.goto(f"{WEB}/office/pensions")
    da.get_by_label("PPO No.").fill("PPO-DEMO-0002")
    da.get_by_role("button", name="Search").click()
    da.get_by_role("button", name="Pension Payment Details").click()
    da.screenshot(path=str(SHOTS / "p2-pension-office.png"), full_page=True)


def test_pensioner_self_service(persona):
    pensioner = persona("pensioner-a", "/pensioner/services")
    status, r = call(pensioner, "POST", "/api/v1/pensioners/me/life-certificate/submissions", {"face_authentication_consent": True})
    assert status == 201 and r["data"]["mock"] is True, r
    lc = call(pensioner, "GET", "/api/v1/pensioners/me/life-certificate")[1]["data"]
    assert lc["state"] == "VALID" and lc["reference"] == r["data"]["pramaan_id"]
    ppo = call(pensioner, "GET", "/api/v1/pensioners/me/ppo")[1]["data"]
    assert ppo["ppo_id"] == "PPO-DEMO-0001"
    slip = call(pensioner, "GET", "/api/v1/pensioners/me/pension-slips?month=2026-08")[1]["data"]
    assert slip["net_paise"] > 0
    account = f"{secrets.randbelow(10**11):011d}1"
    status, req = call(pensioner, "POST", "/api/v1/pensioners/me/bank-change-requests", {"ifsc": "DEMO0000901", "account_number": account},
                       {"X-Step-Up-Token": step_up(pensioner, "change-pension-bank", "PPO-DEMO-0001")})
    assert status == 201, req
    settle(persona("ro-pension", "/office/pensions"), req["data"]["activity_id"], "Bank letter checked")
    assert call(pensioner, "GET", "/api/v1/pensioners/me/ppo")[1]["data"]["disbursing_bank"]["account_last4"] == account[-4:]
    assert call(pensioner, "POST", "/api/v1/pensioners/me/declarations", {"kind": "NON_EMPLOYMENT", "declared": True})[0] == 201
    pensioner.goto(f"{WEB}/pensioner/services")
    pensioner.get_by_role("heading", name="Pension Payment Order").wait_for()
    pensioner.screenshot(path=str(SHOTS / "p2-pensioner-services.png"), full_page=True)


def test_public_pension_enquiries_need_the_demo_question(persona):
    visitor = persona("member-a", "/public")                          # any browser; the enquiries need no login

    def ask(path, body):
        challenge = call(visitor, "GET", "/api/v1/public/demo-challenges")[1]["data"]
        a, b = map(int, re.findall(r"\d+", challenge["prompt"])[:2])
        return call(visitor, "POST", path, {**body, "challenge_id": challenge["challenge_id"], "answer": a + b})
    assert call(visitor, "POST", "/api/v1/public/pension/status-enquiries", {"ppo_id": "PPO-DEMO-0001"})[0] in (400, 422)   # no question answered
    status, r = ask("/api/v1/public/pension/ppo-lookups", {"uan": "100000000901", "date_of_birth": "1965-05-10"})
    assert status == 200 and r["data"]["ppo_id"] == "PPO-DEMO-0001" and "*" in r["data"]["name"], r
    status, r = ask("/api/v1/public/pension/status-enquiries", {"ppo_id": "PPO-DEMO-0001"})
    assert status == 200 and r["data"]["pension_status"] == "Active"
    status, r = ask("/api/v1/public/pension/payment-enquiries", {"ppo_id": "PPO-DEMO-0001", "date_of_birth": "1965-05-10"})
    assert status == 200 and r["data"]["months"] and "amount" not in str(r["data"]["months"])
    status, r = ask("/api/v1/public/pension/life-certificate-lookups", {"ppo_id": "PPO-DEMO-0001"})
    assert status == 200 and r["data"]["state"] == "VALID"
