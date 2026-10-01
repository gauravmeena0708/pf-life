"""Phase 2, slice 12c on the running stack: the APFC (Pension) approves member H's validated higher-pension option and
the DA (Accounts) moves the dues from the PF to the pension fund (posted, or refused for want of balance); a Special 10D
case for incomplete records; the month's bank-wise disbursement lists; the de-identified actuarial extract.
Repeatable: the option and MOHAN DEMO's Special 10D case carry on from an earlier run."""
import re
import uuid

from tests.e2e.test_higher_pension_international_edli import test_joint_option_for_higher_pension_validated_by_the_employer as ensure_validated
from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)

UAN_H = "100000000906"
LATER = ("APPROVED", "TRANSFER_REQUESTED", "DUES_TRANSFERRED", "TRANSFER_FAILED")


def test_higher_pension_option_decided_and_dues_moved(persona):
    apfc = persona("ro-pension", "/office/pensions")
    options = [o for o in call(apfc, "GET", "/api/v1/office/pensions/higher-pension-options")[1]["data"] if o["uan"] == UAN_H]
    if not options:
        ensure_validated(persona)                                                   # member H opts; the employer validates
        options = [o for o in call(apfc, "GET", "/api/v1/office/pensions/higher-pension-options")[1]["data"] if o["uan"] == UAN_H]
    option = options[0]
    oid = option["option_id"]
    if option["state"] == "VALIDATED":
        assert call(apfc, "POST", f"/api/v1/office/pensions/higher-pension-options/{oid}/decisions", {"decision": "APPROVE", "note": "Wages verified"})[0] == 428
        status, r = call(apfc, "POST", f"/api/v1/office/pensions/higher-pension-options/{oid}/decisions",
                         {"decision": "APPROVE", "note": "Wages verified against the payroll register"},
                         {"X-Step-Up-Token": step_up(apfc, "decide-higher-pension", oid, None, option["dues_paise"])})
        assert status == 200 and r["data"]["state"] == "APPROVED", r
    da = persona("do-caseworker", "/office/claim-tools")
    state = call(da, "GET", "/api/v1/office/pensions/higher-pension-options")[1]["data"]
    state = next(o for o in state if o["option_id"] == oid)["state"]
    assert state in LATER
    if state == "APPROVED":
        key = str(uuid.uuid4())
        token = step_up(da, "transfer-higher-pension-dues", oid, None, option["dues_paise"])
        status, r = call(da, "POST", f"/api/v1/office/pensions/higher-pension-options/{oid}/ledger-transfers", None,
                         {"X-Step-Up-Token": token, "Idempotency-Key": key})
        assert status == 200 and r["data"]["state"] == "TRANSFER_REQUESTED", r
    final = wait_for(lambda: next(o for o in call(da, "GET", "/api/v1/office/pensions/higher-pension-options")[1]["data"]
                                  if o["option_id"] == oid)["state"] in ("DUES_TRANSFERRED", "TRANSFER_FAILED") or None, timeout=40)
    assert final
    member = persona("member-h", "/member/higher-pension")
    mine = call(member, "GET", f"/api/v1/members/me/higher-pension-options/{oid}")[1]["data"]
    assert mine["state"] in ("DUES_TRANSFERRED", "TRANSFER_FAILED") and mine["next_step"], mine


def test_special_10d_disbursement_lists_and_actuarial_extract(persona):
    da = persona("ro-da-pension", "/office/pensions")
    uan = "100000000910"                                                          # MOHAN DEMO, left in 2019
    body = {"uan": uan, "missing": ["SERVICE_PERIOD", "WAGES"], "details": "Service before 2002 is missing from the records (synthetic).",
            "evidence": [{"kind": "EMPLOYER_CERTIFICATE", "ref": "EC-2002-17"}]}
    status, r = call(da, "POST", "/api/v1/office/pensions/special-10d-cases", body)
    assert (status == 201 and r["data"]["state"] == "OPEN" and len(r["data"]["checklist"]) == 2) or status == 409, r   # open since an earlier run
    assert call(da, "POST", "/api/v1/office/pensions/special-10d-cases", body)[0] == 409                             # one open case per UAN

    section = persona("ro-pension-disbursement", "/office/pension-disbursement")
    status, r = call(section, "GET", "/api/v1/office/pensions/disbursement-lists")
    assert status == 200 and isinstance(r["data"]["banks"], list) and r["data"]["month"], r
    assert call(section, "GET", "/api/v1/office/pensions/disbursement-lists?month=2026-13")[0] in (400, 422)

    actuary = persona("ho-actuarial", "/ho/actuarial")
    status, r = call(actuary, "GET", "/api/v1/ho/actuarial/extracts")
    assert status == 200 and r["data"]["rows"], r
    text = str(r["data"])
    assert not re.search(r"\b1000000009\d\d\b", text) and "PPO-DEMO" not in text and "DEMO" not in text.upper().replace("DEMO-RULES", ""), "identifiers leaked"
    assert call(da, "GET", "/api/v1/ho/actuarial/extracts")[0] == 403
