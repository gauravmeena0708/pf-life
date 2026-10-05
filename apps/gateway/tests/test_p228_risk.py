from types import SimpleNamespace

import pytest
import respx
from httpx import Response

from conftest import login_as
from app.risk import fingerprint


@pytest.mark.asyncio
async def test_a_new_device_alone_passes_but_with_a_recent_security_event_needs_step_up(client):
    http, app, redis = client
    sid, session = await login_as(app, "member", "member-risk")
    cookies = {"__Host-epfo-session": sid, "epfo-csrf": session["csrf"]}
    headers = {"User-Agent": "new-browser", "X-CSRF-Token": session["csrf"]}
    path = "/api/v1/members/me/nominations"
    with respx.mock() as router:
        upstream = router.get("http://member-service:8000/api/v1/members/me/nominations").mock(
            return_value=Response(200, json={"data": []}))
        assert (await http.get(path, cookies=cookies, headers=headers)).status_code == 200      # one signal: not challenged
        await redis.setex("risk:security-event:member-risk", 60, "1")                          # e.g. an account recovery
        blocked = await http.get(path, cookies=cookies, headers=headers)
        assert blocked.status_code == 428
        assert blocked.json()["type"] == "/problems/step-up-required"
        assert sorted(blocked.json()["reason_codes"]) == ["new-device", "recent-security-event"]
        assert upstream.call_count == 1
        challenge = (await http.post("/api/v1/security/step-up-challenges", cookies=cookies, headers=headers,
                                    json={"action": blocked.json()["action"],
                                          "resource_id": blocked.json()["resource_id"],
                                          "summary": "View nominations"})).json()["data"]
        confirmed = (await http.post(f"/api/v1/security/step-up-challenges/{challenge['challenge_id']}/verifications",
                                     cookies=cookies, headers=headers, json={"otp": challenge["demo_otp"]})).json()["data"]
        allowed = await http.get(path, cookies=cookies,
                                 headers={**headers, "X-Step-Up-Token": confirmed["step_up_token"]})
        assert allowed.status_code == 200
        assert (await http.get(path, cookies=cookies, headers=headers)).status_code == 200    # device now known: one signal
        assert upstream.call_count == 3
    assert not any(b"new-browser" in value for value in await redis.keys("risk:device:*"))


@pytest.mark.asyncio
async def test_always_step_up_route_still_requires_confirmation(client):
    http, app, _ = client
    sid, session = await login_as(app, "member")
    response = await http.patch("/api/v1/members/me/contact-details",
                                cookies={"__Host-epfo-session": sid, "epfo-csrf": session["csrf"]},
                                headers={"X-CSRF-Token": session["csrf"], "User-Agent": "known-browser"})
    assert response.status_code == 428
    assert response.json()["type"] == "/problems/step-up-required"


@pytest.mark.asyncio
async def test_a_known_device_needs_two_signals(client):
    http, app, redis = client
    sid, session = await login_as(app, "member", "member-signals")
    headers = {"User-Agent": "recognised-browser"}
    request = SimpleNamespace(app=app, client=SimpleNamespace(host="127.0.0.1"), headers={"user-agent": "recognised-browser"})
    await redis.setex(f"risk:device:member-signals:{fingerprint(request)}", 30 * 86400, "1")
    cookies = {"__Host-epfo-session": sid}
    with respx.mock() as router:
        router.get("http://member-service:8000/api/v1/members/me/nominations").mock(
            return_value=Response(200, json={"data": []}))
        await redis.setex("risk:security-event:member-signals", 60, "1")
        assert (await http.get("/api/v1/members/me/nominations", cookies=cookies, headers=headers)).status_code == 200
        await redis.set("risk:count:member-signals", 29)                                     # a busy hour as well
        busy = await http.get("/api/v1/members/me/nominations", cookies=cookies, headers=headers)
        assert busy.status_code == 428
        assert sorted(busy.json()["reason_codes"]) == ["recent-security-event", "unusual-activity"]
