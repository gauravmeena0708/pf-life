"""Existing duplicate-UAN detection is a guard for the later cross-service merge."""
from tests.test_member_api import SEED, api  # noqa: F401
from tests.test_onboarding import JOINEE, operator


def test_registration_refuses_second_uan_for_existing_identity(api):
    member = SEED["members"][1]
    r = api.post("/api/v1/employers/me/members", headers=operator(), json={
        **JOINEE, "name": member["name"], "date_of_birth": member["date_of_birth"]})
    assert r.status_code == 409
    assert r.json()["type"] == "/problems/possible-duplicate"
