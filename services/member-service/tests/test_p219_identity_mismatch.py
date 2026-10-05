"""P2.19: identity discrepancies must name the field and the correction route."""
from tests.test_member_api import MEMBER_B, api, token  # noqa: F401


def test_member_sees_each_mismatched_field_and_joint_declaration_route(api):
    r = api.post("/api/v1/members/me/identity-checks", headers=token(MEMBER_B), json={
        "name": "Bharat Kumar Demo", "date_of_birth": "1986-11-02", "gender": "FEMALE"})
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["mismatched_fields"] == ["NAME", "DATE_OF_BIRTH", "GENDER"]
    assert data["correction_path"] == "/members/me/joint-declarations"
    assert data["claim_ready"] is False


def test_matching_identity_has_no_correction(api):
    r = api.post("/api/v1/members/me/identity-checks", headers=token(MEMBER_B), json={
        "name": "  bharat demo ", "date_of_birth": "1985-11-02", "gender": "MALE"})
    assert r.status_code == 200, r.json()
    assert r.json()["data"]["mismatched_fields"] == []
