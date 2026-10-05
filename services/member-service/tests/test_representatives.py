"""P2.24: Tests for Authorised Representatives in member-service."""
from datetime import UTC, date, datetime, timedelta
import time
import uuid

import jwt
import pytest

from tests.conftest import KEY, KID
from tests.test_member_api import SEED, api  # noqa: F401
from tests.test_member_processes import outbox

MEMBER_A = SEED["keycloak_subjects"]["member-a"]
REP_SUBJECT = "00000000-0000-4000-8000-000000000083"


def member_hdr(subject=MEMBER_A):
    now = int(time.time())
    claims = {
        "iss": "epfo-gateway",
        "aud": "member-service",
        "sub": subject,
        "stakeholder": "member",
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def rep_hdr(subject=REP_SUBJECT):
    now = int(time.time())
    claims = {
        "iss": "epfo-gateway",
        "aud": "member-service",
        "sub": subject,
        "stakeholder": "member.representative",
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def gw_hdr():
    now = int(time.time())
    claims = {
        "iss": "epfo-gateway",
        "aud": "member-service",
        "sub": "gateway",
        "stakeholder": "system.gateway",
        "iat": now,
        "exp": now + 60,
        "jti": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def test_grant_within_scopes_and_notification(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=180)).isoformat()
    payload = {
        "representative_subject": REP_SUBJECT,
        "relation": "GUARDIAN",
        "scopes": ["VIEW_PROFILE", "VIEW_PASSBOOK", "TRACK_GRIEVANCES"],
        "valid_until": valid_until,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 201, res.json()
    data = res.json()["data"]
    assert data["grant_id"].startswith("REP-")
    assert data["representative_subject"] == REP_SUBJECT
    assert data["relation"] == "GUARDIAN"
    assert data["scopes"] == ["VIEW_PROFILE", "VIEW_PASSBOOK", "TRACK_GRIEVANCES"]
    assert data["state"] == "ACTIVE"
    assert data["valid_until"] == valid_until

    # Check notification outbox
    notifications = [n for n in outbox("NotificationRequested.v1") if n.get("template") == "REPRESENTATIVE_GRANTED"]
    assert len(notifications) >= 1
    assert notifications[-1]["recipient_subject"] == MEMBER_A


def test_grant_by_username(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    payload = {
        "representative_username": "rep-demo",
        "relation": "AGENT",
        "scopes": ["VIEW_CLAIMS", "RAISE_GRIEVANCE"],
        "valid_until": valid_until,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 201, res.json()
    assert res.json()["data"]["representative_subject"] == REP_SUBJECT


def test_refuse_unknown_scope(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    payload = {
        "representative_subject": REP_SUBJECT,
        "relation": "AGENT",
        "scopes": ["VIEW_PROFILE", "FILE_CLAIM_TRANSFER"],  # illegal scope
        "valid_until": valid_until,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 400
    assert "Invalid scope" in res.json().get("detail", "")


def test_refuse_exceeding_one_year(api):
    too_far = (datetime.now(UTC).date() + timedelta(days=400)).isoformat()
    payload = {
        "representative_subject": REP_SUBJECT,
        "relation": "AGENT",
        "scopes": ["VIEW_PROFILE"],
        "valid_until": too_far,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 400
    assert "cannot exceed 1 year" in res.json().get("detail", "")


def test_refuse_past_date(api):
    past = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    payload = {
        "representative_subject": REP_SUBJECT,
        "relation": "AGENT",
        "scopes": ["VIEW_PROFILE"],
        "valid_until": past,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 400
    assert "future" in res.json().get("detail", "")


def test_refuse_invalid_relation(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    payload = {
        "representative_subject": REP_SUBJECT,
        "relation": "LAWYER",
        "scopes": ["VIEW_PROFILE"],
        "valid_until": valid_until,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 400
    assert "Invalid relation" in res.json().get("detail", "")


def test_refuse_unknown_username(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    payload = {
        "representative_username": "non-existent-user-12345",
        "relation": "AGENT",
        "scopes": ["VIEW_PROFILE"],
        "valid_until": valid_until,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 400


def test_refuse_self_representation(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=90)).isoformat()
    payload = {
        "representative_subject": MEMBER_A,
        "relation": "AGENT",
        "scopes": ["VIEW_PROFILE"],
        "valid_until": valid_until,
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 400


def test_refuse_non_representative_subject(api):
    payload = {
        "representative_subject": SEED["keycloak_subjects"]["emp-owner"],
        "relation": "AGENT", "scopes": ["VIEW_PROFILE"],
        "valid_until": (datetime.now(UTC).date() + timedelta(days=30)).isoformat(),
    }
    res = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr())
    assert res.status_code == 400


def test_list_and_revoke_representative(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=60)).isoformat()
    payload = {
        "representative_subject": REP_SUBJECT,
        "relation": "AGENT",
        "scopes": ["VIEW_SERVICE_HISTORY"],
        "valid_until": valid_until,
    }
    created = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr()).json()["data"]
    grant_id = created["grant_id"]

    # List representatives
    listed = api.get("/api/v1/members/me/representatives", headers=member_hdr())
    assert listed.status_code == 200
    grants = listed.json()["data"]
    match = next((g for g in grants if g["grant_id"] == grant_id), None)
    assert match is not None
    assert match["state"] == "ACTIVE"

    # Revoke
    rev = api.post(f"/api/v1/members/me/representatives/{grant_id}/revocations", headers=member_hdr())
    assert rev.status_code == 200
    assert rev.json()["data"]["state"] == "REVOKED"
    assert rev.json()["data"]["revoked_at"] is not None

    # Check notification outbox
    notifications = [n for n in outbox("NotificationRequested.v1") if n.get("template") == "REPRESENTATIVE_REVOKED"]
    assert len(notifications) >= 1

    # Re-list shows REVOKED
    listed_after = api.get("/api/v1/members/me/representatives", headers=member_hdr()).json()["data"]
    match_after = next(g for g in listed_after if g["grant_id"] == grant_id)
    assert match_after["state"] == "REVOKED"


def test_representative_me_members_and_internal_grants(api):
    valid_until = (datetime.now(UTC).date() + timedelta(days=120)).isoformat()
    payload = {
        "representative_subject": REP_SUBJECT,
        "relation": "GUARDIAN",
        "scopes": ["VIEW_PROFILE", "VIEW_PASSBOOK"],
        "valid_until": valid_until,
    }
    created = api.post("/api/v1/members/me/representatives", json=payload, headers=member_hdr()).json()["data"]
    grant_id = created["grant_id"]

    # Representative views active members
    rep_res = api.get("/api/v1/representatives/me/members", headers=rep_hdr(REP_SUBJECT))
    assert rep_res.status_code == 200, rep_res.json()
    rep_data = rep_res.json()["data"]
    match = next((m for m in rep_data if m["grant_id"] == grant_id), None)
    assert match is not None
    assert match["relation"] == "GUARDIAN"
    assert match["scopes"] == ["VIEW_PROFILE", "VIEW_PASSBOOK"]
    assert match["member_name"] is not None

    # Gateway internal endpoint
    gw_res = api.get(f"/internal/representatives/{REP_SUBJECT}/grants", headers=gw_hdr())
    assert gw_res.status_code == 200, gw_res.json()
    gw_grants = gw_res.json()["data"]["grants"]
    gw_match = next((g for g in gw_grants if g["grant_id"] == grant_id), None)
    assert gw_match is not None
    assert gw_match["member_subject"] == MEMBER_A
    assert gw_match["scopes"] == ["VIEW_PROFILE", "VIEW_PASSBOOK"]

    # Now revoke and verify it disappears from active lists
    api.post(f"/api/v1/members/me/representatives/{grant_id}/revocations", headers=member_hdr())

    rep_after = api.get("/api/v1/representatives/me/members", headers=rep_hdr(REP_SUBJECT)).json()["data"]
    assert not any(m["grant_id"] == grant_id for m in rep_after)

    gw_after = api.get(f"/internal/representatives/{REP_SUBJECT}/grants", headers=gw_hdr()).json()["data"]["grants"]
    assert not any(g["grant_id"] == grant_id for g in gw_after)
