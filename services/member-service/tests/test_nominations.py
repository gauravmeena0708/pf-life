"""e-Nomination, Know your UAN, and approved employer corrections to a recorded exit."""
import asyncio
from datetime import date

import pytest
from sqlalchemy import select

from tests.test_exits import hdr
from tests.test_member_api import MEMBER_A, MEMBER_B, SEED, api  # noqa: F401  (api is a fixture)
from tests.test_member_processes import deliver, outbox

MEMBER = SEED["members"][0]
NOMINATIONS = "/api/v1/members/me/nominations"


def nomination():
    return {"has_family": True, "nominees": [
        {"name": "  spouse demo  ", "relation": "SPOUSE", "date_of_birth": "1990-01-01", "share_bp": 6000},
        {"name": "child demo", "relation": "DAUGHTER", "date_of_birth": date.today().isoformat(),
         "share_bp": 4000, "guardian_name": "  spouse demo  "},
    ]}


def sign(api, body, member=MEMBER):
    return api.post(NOMINATIONS, json=body,
                    headers=hdr(member["subject"], {"action": "e-nominate", "resource_id": member["uan"]}))


def stored_nominations(uan):
    import app.infra.db as db
    from app.infra.tables import nominations

    async def run():
        async with db.sessions()() as session:
            rows = (await session.execute(select(nominations).where(nominations.c.uan == uan))).mappings().all()
            return {r["nomination_id"]: dict(r) for r in rows}

    return asyncio.run(run())


def test_nomination_is_current_published_and_supersedes_the_previous_one(api):
    initial = api.get(NOMINATIONS, headers=hdr(MEMBER_A))
    assert initial.status_code == 200
    before = initial.json()["data"]
    assert before["uan"] == MEMBER["uan"] and before["aadhaar_verified"] is True

    response = sign(api, nomination())
    assert response.status_code == 201, response.json()
    first = response.json()["data"]
    assert first["state"] == "CURRENT" and first["has_family"] is True
    assert first["signed_with"] == "MOCK_AADHAAR_ESIGN" and first["signed_at"]
    assert first["nominees"] == [
        {"name": "SPOUSE DEMO", "relation": "SPOUSE", "date_of_birth": "1990-01-01", "share_bp": 6000,
         "minor": False, "guardian_name": None},
        {"name": "CHILD DEMO", "relation": "DAUGHTER", "date_of_birth": date.today().isoformat(),
         "share_bp": 4000, "minor": True, "guardian_name": "SPOUSE DEMO"},
    ]
    [event] = outbox("NominationRegistered.v1")
    assert event == {"nomination_id": first["nomination_id"], "uan": MEMBER["uan"],
                     "signed_with": "MOCK_AADHAAR_ESIGN",
                     "nominees": [{k: v for k, v in n.items() if k != "date_of_birth"} for n in first["nominees"]]}

    replacement = nomination()
    replacement["nominees"][0]["share_bp"] = 5000
    replacement["nominees"][1]["share_bp"] = 5000
    response = sign(api, replacement)
    assert response.status_code == 201, response.json()
    second = response.json()["data"]
    assert second["nomination_id"] != first["nomination_id"] and second["state"] == "CURRENT"
    current = api.get(NOMINATIONS, headers=hdr(MEMBER_A)).json()["data"]
    assert current["current"] == second
    history = {n["nomination_id"]: n for n in current["history"]}
    assert history[first["nomination_id"]] == {**first, "state": "SUPERSEDED"}
    if before["current"]:
        assert history[before["current"]["nomination_id"]] == {**before["current"], "state": "SUPERSEDED"}
    rows = stored_nominations(MEMBER["uan"])
    assert rows[first["nomination_id"]]["state"] == "SUPERSEDED"
    assert rows[second["nomination_id"]]["has_family"] is True
    assert rows[second["nomination_id"]]["member_id"] == MEMBER["member_id"]
    assert [r["nomination_id"] for r in rows.values() if r["state"] == "CURRENT"] == [second["nomination_id"]]
    assert len(outbox("NominationRegistered.v1")) == 2
    assert outbox("NominationRegistered.v1")[1]["nomination_id"] == second["nomination_id"]
    other = api.get(NOMINATIONS, headers=hdr(MEMBER_B)).json()["data"]
    assert other["current"] is None and other["history"] == []


@pytest.mark.parametrize("invalid, detail", [
    ("shares", "must add up to 100%"),
    ("relation", "only family members"),
    ("guardian", "guardian's name"),
    ("aadhaar", "verified Aadhaar"),
])
def test_invalid_nomination_is_refused_without_replacing_or_publishing(api, invalid, detail):
    body = nomination()
    member = MEMBER
    if invalid == "shares":
        body["nominees"][0]["share_bp"] = 5999
    elif invalid == "relation":
        body["nominees"][0]["relation"] = "OTHER"
    elif invalid == "guardian":
        del body["nominees"][1]["guardian_name"]
    else:
        member = next(m for m in SEED["members"] if m["subject"] and m["kyc"]["aadhaar"] != "VERIFIED")
    before = stored_nominations(member["uan"])
    response = sign(api, body, member)
    assert response.status_code == 422, response.json()
    problem = response.json()
    assert problem["type"] == "/problems/nomination-invalid" and detail in problem["detail"]
    assert any(detail in error for error in problem["errors"])
    assert stored_nominations(member["uan"]) == before
    assert outbox("NominationRegistered.v1") == []


@pytest.mark.parametrize("step_up, status, problem_type", [
    (None, 428, "/problems/step-up-required"),
    ({"action": "mark-exit", "resource_id": MEMBER["uan"]}, 403, "/problems/step-up-mismatch"),
    ({"action": "e-nominate", "resource_id": SEED["members"][1]["uan"]}, 403, "/problems/step-up-mismatch"),
])
def test_nomination_requires_step_up_for_this_action_and_uan(api, step_up, status, problem_type):
    before = stored_nominations(MEMBER["uan"])
    response = api.post(NOMINATIONS, json=nomination(), headers=hdr(MEMBER_A, step_up))
    assert response.status_code == status, response.json()
    assert response.json()["type"] == problem_type
    assert stored_nominations(MEMBER["uan"]) == before
    assert outbox("NominationRegistered.v1") == []


def lookup_body():
    member = SEED["members"][1]                     # another UAN has the same name and date of birth
    return {"name": f"  {member['name'].lower()}  ", "date_of_birth": member["date_of_birth"],
            "mobile_last4": member["mobile_masked"][-4:], "otp": "123456"}


def test_uan_lookup_matches_case_insensitive_name_birth_date_and_mobile(api):
    response = api.post("/api/v1/members/uan-lookups", json=lookup_body(), headers=hdr(MEMBER_A))
    assert response.status_code == 200, response.json()
    result = response.json()["data"]
    assert result["found"] == [{"uan": SEED["members"][1]["uan"], "aadhaar_verified": True,
                                "latest_establishment": SEED["establishment"]["legal_name"], "status": "ACTIVE"}]
    assert result["sent_to"] == "******0002 (mock SMS)"


@pytest.mark.parametrize("field, value", [
    ("name", "Unknown Member"), ("date_of_birth", "1900-01-01"), ("mobile_last4", "9999"),
])
def test_uan_lookup_requires_all_three_details_to_match(api, field, value):
    response = api.post("/api/v1/members/uan-lookups", json={**lookup_body(), field: value}, headers=hdr(MEMBER_A))
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["found"] == []


def test_uan_lookup_refuses_the_invalid_mock_otp(api):
    response = api.post("/api/v1/members/uan-lookups", json={**lookup_body(), "otp": "000000"}, headers=hdr(MEMBER_A))
    assert response.status_code == 422, response.json()
    assert response.json()["type"] == "/problems/otp-invalid"


def test_approved_employer_exit_correction_updates_employment_and_publishes_corrects(api):
    payload = {"process": "employer_exit", "instance_id": "CASE-EXIT-ORIGINAL", "subject_ref": MEMBER["uan"],
               "from_state": "EXIT_MARKED", "to_state": "APPROVED", "operation": "approve", "terminal": True,
               "visible_to_member": True, "title": "Date of exit (employer)",
               "actor_subject": "signatory", "actor_role": "employer.signatory",
               "data": {"account_link_id": MEMBER["account_link_id"], "date_of_exit": "2026-08-31", "reason": "CESSATION"}}
    assert deliver(payload)[0]
    [original] = outbox("MemberExitMarked.v1")
    assert original["date_of_exit"] == "2026-08-31" and "corrects" not in original
    history = api.get("/api/v1/members/me/employment-history", headers=hdr(MEMBER_A)).json()["data"]
    assert next(j for j in history if j["account_link_id"] == MEMBER["account_link_id"])["date_of_exit"] == "2026-08-31"

    correction = {**payload, "instance_id": "CASE-EXIT-CORRECTION", "data": {
        **payload["data"], "date_of_exit": "2026-08-30", "correction_note": "Correct the date against the attendance record."}}
    assert deliver(correction)[0]
    assert outbox("MemberExitMarked.v1") == [original, {**original, "date_of_exit": "2026-08-30", "corrects": "2026-08-31"}]
    history = api.get("/api/v1/members/me/employment-history", headers=hdr(MEMBER_A)).json()["data"]
    job = next(j for j in history if j["account_link_id"] == MEMBER["account_link_id"])
    assert job["date_of_exit"] == "2026-08-30" and job["exit_marked_by"] == "EMPLOYER"
    assert job["status"] == "EXITED"
    assert deliver(correction)[0]                    # a re-sent approval must not publish another correction
    assert len(outbox("MemberExitMarked.v1")) == 2
