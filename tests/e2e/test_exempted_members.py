"""Phase 2, slice 9b on the running stack: members of an exempted establishment (Demo Steel Works, PF with its trust).
Member P moves her earlier EPFO member ID into the trust — the PF leg is sent to the trust and the pension (EPS) leg
completes inside EPFO; member R moves his PF out of the trust — the PF leg waits for the trust's Annexure K, the office
reconciles it, and the EPS leg then starts on its own. The trust's passbook is read from the trust; PF claims on a
trust member ID go to the trust. Repeatable: a transfer already made is checked rather than made again."""
import uuid

from tests.e2e.test_journey_a_ecr import call, step_up, wait_for
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def legs(member, uan_from):
    return next((t for t in call(member, "GET", "/api/v1/members/me/transfer-legs")[1]["data"]["transfers"] if t["from_account_link_id"] == uan_from), None)


def form13(persona, member, uan, frm, to, signatory_name):
    """Member asks, the present employer attests, the DA verifies (after viewing the signed Form 13), the AO approves."""
    body = {"from_account_link_id": frm, "to_account_link_id": to, "attesting_employer": "PRESENT"}
    open_case = next((a for a in call(member, "GET", "/api/v1/members/me/applications?status=pending")[1]["data"]
                      if a["process"] == "transfer_form13"), None)
    if open_case:
        case = call(member, "GET", f"/api/v1/members/me/transfers/{open_case['application_id']}")[1]["data"]
    else:
        status, r = call(member, "POST", "/api/v1/members/me/transfers", body, {"X-Step-Up-Token": step_up(member, "submit-transfer", uan)})
        assert status == 200, r
        case = r["data"]
    if case["state"] == "SUBMITTED":
        signatory = persona(signatory_name, "/employer/members")
        queued = wait_for(lambda: next((c for c in call(signatory, "GET", "/api/v1/employers/me/transfer-requests")[1]["data"]
                                        if c["case_id"] == case["case_id"]), None))
        status, r = call(signatory, "POST", f"/api/v1/employers/me/transfer-requests/{case['case_id']}/decisions",
                         {"decision": "ATTEST", "note": "Present employee"},
                         {"X-Step-Up-Token": step_up(signatory, "attest-transfer", case["case_id"], queued["version"])})
        assert status == 200, r
        case = r["data"]
    if case["state"] == "EMPLOYER_ATTESTED":
        da = persona("do-caseworker", "/office/work-queue")
        for doc in call(da, "GET", f"/api/v1/office/cases/{case['case_id']}")[1]["data"]["documents"]:
            call(da, "POST", f"/api/v1/office/cases/{case['case_id']}/documents/{doc['doc_id']}/attestation-views")
        status, r = call(da, "POST", f"/api/v1/office/transfers/{case['case_id']}/verifications",
                         {"service_checked": "YES", "note": "Service at both establishments checked"})
        assert status == 200, r
        case = r["data"]
    if case["state"] == "VERIFIED":
        ao = persona("ro-ao", "/office/work-queue")
        status, r = call(ao, "POST", f"/api/v1/office/transfers/{case['case_id']}/decisions",
                         {"decision": "APPROVE", "reason": "Service and balance verified"},
                         {"X-Step-Up-Token": step_up(ao, "decide-transfer", case["case_id"], case["version"])})
        assert status == 200 and r["data"]["state"] == "APPROVED", r


def test_member_p_moves_her_epfo_member_id_into_the_trust(persona):
    member = persona("member-p", "/member/service")
    passbook = call(member, "GET", "/api/v1/members/me/passbook")[1]["data"]
    assert "Demo Steel Works" in str(passbook) and "trust" in str(passbook).lower(), passbook       # the trust's section, read from the trust
    eligible = call(member, "GET", "/api/v1/members/me/claims/eligible-types")[1]["data"]["accounts"]
    at_trust = next(a for a in eligible if a["account_link_id"] == "AL-0915")
    settlement = next(t for t in at_trust["types"] if t["claim_type"] == "FINAL_SETTLEMENT")
    assert not settlement["eligible"] and any("with Demo Steel Works" in r for r in settlement["reasons"]), settlement
    if not legs(member, "AL-0914"):
        form13(persona, member, "100000000911", "AL-0914", "AL-0915", "steel-signatory")
    final = wait_for(lambda: (lambda t: t if t and t["eps_leg"]["state"] == "COMPLETED" else None)(legs(member, "AL-0914")), timeout=40)
    assert final["direction"] == "EPFO_TO_TRUST" and final["pf_leg"]["state"] == "SENT_TO_TRUST", final


def test_member_r_moves_his_pf_out_of_the_trust_and_the_pension_follows(persona):
    member = persona("member-r", "/member/service")
    if not legs(member, "AL-0918"):
        form13(persona, member, "100000000912", "AL-0918", "AL-0919", "emp-signatory")
    first = wait_for(lambda: legs(member, "AL-0918"), timeout=30)
    assert first["direction"] == "TRUST_TO_EPFO"
    if first["pf_leg"]["state"] != "COMPLETED":
        assert first["eps_leg"]["state"] == "WAITING_FOR_PF", first          # the pension waits for the trust's PF
        trust = persona("exempted-trust", "/exempted")
        assert "17(1)(a)" in str(call(trust, "GET", "/api/v1/exempted/me/profile")[1]["data"])
        request = wait_for(lambda: next((r for r in call(trust, "GET", "/api/v1/exempted/me/annexure-k-requests")[1]["data"]["requests"]
                                         if r["transfer_id"] == first["transfer_id"]), None), timeout=30)
        if request["state"] == "REQUESTED":
            status, r = call(trust, "POST", "/api/v1/exempted/me/annexure-k-submissions",
                             {"annexure_id": request["annexure_id"], "employee_paise": 52000000, "employer_paise": 19000000,
                              "service_from": "2015-01-01", "service_to": "2026-06-30", "breaks_months": 2},
                             {"Idempotency-Key": str(uuid.uuid4())})
            assert status == 201, r
        da = persona("do-caseworker", "/office/claim-tools")
        aid = request["annexure_id"]
        status, r = call(da, "POST", f"/api/v1/office/exempted/annexure-k/{aid}/reconciliations",
                         {"receipt_ref": "TRUST-RTGS-0001", "received_paise": 71000000},
                         {"X-Step-Up-Token": step_up(da, "reconcile-trust-annexure-k", aid, None, 71000000)})
        assert status == 200 and r["data"]["state"] == "MATCHED", r
    final = wait_for(lambda: (lambda t: t if t["pf_leg"]["state"] == "COMPLETED" and t["eps_leg"]["state"] == "COMPLETED" else None)(
        legs(member, "AL-0918")), timeout=40)
    assert final["eps_leg"]["state"] == "COMPLETED"                                 # started on its own once the PF arrived
    estimate = call(member, "GET", "/api/v1/members/me/pension-eligibility-preview")[1]["data"]
    by_id = {x["account_link_id"]: x for x in estimate["service_by_member_id"]}
    assert set(by_id) >= {"AL-0918", "AL-0919"} and by_id["AL-0918"]["breaks_months"] == 2, by_id
