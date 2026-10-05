"""P2.24: representative consent is enforced before catalogue callers checks."""
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import respx
from httpx import Response

from app import representation
from conftest import login_as

GRANT = {"grant_id": "REP-1", "member_subject": "member-a", "relation": "AGENT",
         "scopes": ["VIEW_PASSBOOK", "RAISE_GRIEVANCE"], "state": "ACTIVE",
         "valid_until": (datetime.now(UTC).date() + timedelta(days=30)).isoformat()}


@pytest.mark.asyncio
async def test_in_scope_forwarded_as_member_with_actor(client):
    representation.forget()
    http, app, _ = client
    sid, _ = await login_as(app, "member.representative", "rep-1")
    seen = {}
    with respx.mock(assert_all_called=False) as router:
        grants = router.get("http://member-service:8000/internal/representatives/rep-1/grants").mock(
            return_value=Response(200, json={"data": {"grants": [GRANT]}}))
        def upstream(req):
            seen["claims"] = jwt.decode(req.headers["authorization"].split()[1], options={"verify_signature": False})
            seen["header"] = req.headers.get("x-acting-for")
            return Response(200, json={"data": []})
        router.get("http://contribution-service:8000/api/v1/members/me/passbook").mock(side_effect=upstream)
        for _ in range(2):
            result = await http.get("/api/v1/members/me/passbook", cookies={"__Host-epfo-session": sid},
                                    headers={"X-Acting-For": "REP-1"})
            assert result.status_code == 200
        assert grants.call_count == 1
    assert seen["claims"]["sub"] == "member-a"
    assert seen["claims"]["stakeholder"] == "member"
    assert seen["claims"]["acted_by"] == {"subject": "rep-1", "grant_id": "REP-1", "relation": "AGENT"}
    assert seen["header"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("path,method,grant,header", [
    ("/members/me/claims", "GET", GRANT, "REP-1"),
    ("/members/me/contact-details", "PATCH", GRANT, "REP-1"),
    ("/members/me/passbook", "GET", {**GRANT, "state": "REVOKED"}, "REP-1"),
    ("/members/me/passbook", "GET", {**GRANT, "valid_until": "2000-01-01"}, "REP-1"),
    ("/members/me/passbook", "GET", GRANT, "REP-OTHER"),
    ("/members/me/passbook", "GET", GRANT, None),
])
async def test_denied_representation(client, path, method, grant, header):
    representation.forget()
    http, app, _ = client
    sid, session = await login_as(app, "member.representative", "rep-1")
    headers = {"X-CSRF-Token": session["csrf"]}
    if header: headers["X-Acting-For"] = header
    with respx.mock(assert_all_called=False) as router:
        router.get("http://member-service:8000/internal/representatives/rep-1/grants").mock(
            return_value=Response(200, json={"data": {"grants": [grant]}}))
        response = await http.request(method, "/api/v1" + path,
                                      cookies={"__Host-epfo-session": sid, "epfo-csrf": session["csrf"]}, headers=headers)
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/representative-not-allowed"


@pytest.mark.asyncio
async def test_member_unchanged_and_own_rep_route_needs_no_header(client):
    http, app, _ = client
    member_sid, _ = await login_as(app, "member", "member-a")
    rep_sid, _ = await login_as(app, "member.representative", "rep-1")
    seen = {}
    with respx.mock() as router:
        def upstream(req):
            seen[req.url.path] = jwt.decode(req.headers["authorization"].split()[1], options={"verify_signature": False})
            return Response(200, json={"data": []})
        router.get("http://contribution-service:8000/api/v1/members/me/passbook").mock(side_effect=upstream)
        router.get("http://member-service:8000/api/v1/representatives/me/members").mock(side_effect=upstream)
        assert (await http.get("/api/v1/members/me/passbook", cookies={"__Host-epfo-session": member_sid})).status_code == 200
        assert (await http.get("/api/v1/representatives/me/members", cookies={"__Host-epfo-session": rep_sid})).status_code == 200
    assert "acted_by" not in seen["/api/v1/members/me/passbook"]
    assert seen["/api/v1/representatives/me/members"]["stakeholder"] == "member.representative"


@pytest.mark.asyncio
async def test_member_revocation_forgets_cached_grant(client):
    representation.forget()
    http, app, _ = client
    rep_sid, _ = await login_as(app, "member.representative", "rep-1")
    member_sid, member_session = await login_as(app, "member", "member-a")
    with respx.mock() as router:
        grants = router.get("http://member-service:8000/internal/representatives/rep-1/grants").mock(
            side_effect=[Response(200, json={"data": {"grants": [GRANT]}}),
                         Response(200, json={"data": {"grants": []}})])
        router.get("http://contribution-service:8000/api/v1/members/me/passbook").mock(
            return_value=Response(200, json={"data": []}))
        router.post("http://member-service:8000/api/v1/members/me/representatives/REP-1/revocations").mock(
            return_value=Response(200, json={"data": {"grant_id": "REP-1", "state": "REVOKED",
                                                      "representative_subject": "rep-1"}}))
        url = "/api/v1/members/me/passbook"
        headers = {"X-Acting-For": "REP-1"}
        assert (await http.get(url, cookies={"__Host-epfo-session": rep_sid}, headers=headers)).status_code == 200
        assert (await http.post("/api/v1/members/me/representatives/REP-1/revocations",
                                cookies={"__Host-epfo-session": member_sid, "epfo-csrf": member_session["csrf"]},
                                headers={"X-CSRF-Token": member_session["csrf"]})).status_code == 200
        denied = await http.get(url, cookies={"__Host-epfo-session": rep_sid}, headers=headers)
        assert denied.status_code == 403
        assert grants.call_count == 2


@pytest.mark.asyncio
async def test_risk_challenged_passbook_is_refused(client, monkeypatch):
    representation.forget()
    http, app, _ = client
    sid, _ = await login_as(app, "member.representative", "rep-1")
    async def risk(*_args):
        return ["new-device", "unusual-activity"]
    monkeypatch.setattr("app.pipeline.assess_risk", risk)
    with respx.mock() as router:
        router.get("http://member-service:8000/internal/representatives/rep-1/grants").mock(
            return_value=Response(200, json={"data": {"grants": [GRANT]}}))
        response = await http.get("/api/v1/members/me/accounts/ACC-1/passbook",
                                  cookies={"__Host-epfo-session": sid}, headers={"X-Acting-For": "REP-1"})
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/representative-not-allowed"
