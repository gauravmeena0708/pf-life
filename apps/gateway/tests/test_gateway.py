import jwt
import json
import time

import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response
from jwt import PyJWK, algorithms

from app.routing import match_route
from conftest import login_as


def test_literal_route_beats_template():
    routes = [
        {"method": "GET", "path_template": "/members/me/claims/{claimId}", "regex": r"^/members/me/claims/[^/]+$"},
        {"method": "GET", "path_template": "/members/me/claims/eligibility-preview", "regex": r"^/members/me/claims/eligibility\-preview$"},
    ]
    assert match_route(routes, "GET", "/members/me/claims/eligibility-preview")["path_template"].endswith("eligibility-preview")

    overlapping = [
        {"method": "GET", "path_template": "/foo/{id}/very-long-literal", "regex": r"^/foo/[^/]+/very-long-literal$"},
        {"method": "GET", "path_template": "/foo/literal/{id}", "regex": r"^/foo/literal/[^/]+$"},
    ]
    assert match_route(overlapping, "GET", "/foo/literal/very-long-literal")["path_template"] == "/foo/literal/{id}"


@pytest.mark.asyncio
async def test_planned_public_route_is_501_without_auth(client):
    http, _, _ = client
    response = await http.get("/api/v1/public/circulars")
    assert response.status_code == 501
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "/problems/planned"
    assert response.json()["correlation_id"]


@pytest.mark.asyncio
async def test_public_working_route_is_served_without_redis(client):
    http, app, redis = client
    async def broken(*args, **kwargs):
        raise ConnectionError("redis unavailable")
    redis.ping = broken
    with respx.mock(assert_all_called=True) as router:
        route = router.get("http://reporting-service:8000/api/v1/public/statistics").mock(
            return_value=Response(200, json={"data": {"synthetic": True}}))
        response = await http.get("/api/v1/public/statistics")
    assert response.status_code == 200
    assert route.called


@pytest.mark.asyncio
async def test_unauthenticated_route_is_401(client):
    http, _, _ = client
    response = await http.get("/api/v1/members/me")
    assert response.status_code == 401
    assert response.json()["type"] == "/problems/unauthenticated"


@pytest.mark.asyncio
async def test_wrong_stakeholder_is_403(client):
    http, app, _ = client
    sid, session = await login_as(app, "member")
    response = await http.get("/api/v1/employers/me", cookies={"__Host-epfo-session": sid})
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/forbidden"


@pytest.mark.asyncio
async def test_protected_planned_route_checks_permission_before_501(client):
    http, app, _ = client
    sid, session = await login_as(app, "ho.security")
    response = await http.post("/api/v1/members/me/nominations",
        cookies={"__Host-epfo-session": sid, "epfo-csrf": session["csrf"]},
        headers={"X-CSRF-Token": session["csrf"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_mutation_requires_double_submit_csrf(client):
    http, app, _ = client
    sid, _ = await login_as(app, "ho.security")
    response = await http.post("/api/v1/security/sessions/test/revocations", cookies={"__Host-epfo-session": sid})
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/csrf"


@pytest.mark.asyncio
async def test_step_up_flow_binds_single_use_token_into_internal_jwt(client):
    http, app, _ = client
    sid, session = await login_as(app, "member", subject="member-1")
    cookies = {"__Host-epfo-session": sid, "epfo-csrf": session["csrf"]}
    headers = {"X-CSRF-Token": session["csrf"]}
    url = "/api/v1/members/me/contact-details"
    assert (await http.patch(url, cookies=cookies, headers=headers)).status_code == 428
    challenge = await http.post("/api/v1/security/step-up-challenges", cookies=cookies, headers=headers,
                                json={"action": "change-contact", "resource_id": "member-1", "summary": "Change mobile"})
    assert challenge.status_code == 200
    c = challenge.json()["data"]
    wrong = await http.post(f"/api/v1/security/step-up-challenges/{c['challenge_id']}/verifications", cookies=cookies,
                            headers=headers, json={"otp": "000000" if c["demo_otp"] != "000000" else "111111"})
    assert wrong.status_code == 403
    ok = await http.post(f"/api/v1/security/step-up-challenges/{c['challenge_id']}/verifications", cookies=cookies,
                         headers=headers, json={"otp": c["demo_otp"]})
    token = ok.json()["data"]["step_up_token"]
    seen = {}
    with respx.mock() as router:
        def reply(request):
            seen["jwt"] = request.headers["authorization"].split()[1]
            return Response(200, json={"data": {}})
        router.patch("http://member-service:8000/api/v1/members/me/contact-details").mock(side_effect=reply)
        first = await http.patch(url, cookies=cookies, headers={**headers, "X-Step-Up-Token": token})
        replay = await http.patch(url, cookies=cookies, headers={**headers, "X-Step-Up-Token": token})
    assert first.status_code == 200
    claims = jwt.decode(seen["jwt"], options={"verify_signature": False})
    assert claims["step_up"] == {"action": "change-contact", "resource_id": "member-1", "resource_version": None,
                                 "amount_paise": None}
    assert replay.status_code == 403 and replay.json()["type"] == "/problems/step-up-invalid"


@pytest.mark.asyncio
async def test_step_up_token_cannot_be_used_by_another_user(client):
    http, app, _ = client
    sid_a, sa = await login_as(app, "member", subject="member-a")
    sid_b, sb = await login_as(app, "member", subject="member-b")
    ca = {"__Host-epfo-session": sid_a, "epfo-csrf": sa["csrf"]}
    c = (await http.post("/api/v1/security/step-up-challenges", cookies=ca, headers={"X-CSRF-Token": sa["csrf"]},
                         json={"action": "x", "resource_id": "r", "summary": "s"})).json()["data"]
    token = (await http.post(f"/api/v1/security/step-up-challenges/{c['challenge_id']}/verifications", cookies=ca,
                             headers={"X-CSRF-Token": sa["csrf"]}, json={"otp": c["demo_otp"]})).json()["data"]["step_up_token"]
    r = await http.patch("/api/v1/members/me/contact-details", cookies={"__Host-epfo-session": sid_b, "epfo-csrf": sb["csrf"]},
                         headers={"X-CSRF-Token": sb["csrf"], "X-Step-Up-Token": token})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_employer_grants_resolved_into_jwt_and_cache_cleared_on_revocation(client):
    from app import grants as grant_resolver
    grant_resolver.forget()
    http, app, redis = client
    sid, session = await login_as(app, "employer.operator", subject="operator-1")
    cookies = {"__Host-epfo-session": sid}
    seen = {}
    with respx.mock() as router:
        grants_route = router.get("http://employer-service:8000/internal/actors/operator-1/grants").mock(
            return_value=Response(200, json={"data": {"establishments": [{"establishment_id": "EST-1", "grants": ["ecr.prepare"]}]}}))
        def reply(request):
            seen["jwt"] = request.headers["authorization"].split()[1]
            return Response(200, json={"data": []})
        router.get("http://contribution-service:8000/api/v1/employers/me/ecr-filings").mock(side_effect=reply)
        assert (await http.get("/api/v1/employers/me/ecr-filings", cookies=cookies)).status_code == 200
        assert (await http.get("/api/v1/employers/me/ecr-filings", cookies=cookies)).status_code == 200
        assert grants_route.call_count == 1  # cached
        grant_resolver.forget("operator-1")   # what a successful revocation does
        await http.get("/api/v1/employers/me/ecr-filings", cookies=cookies)
        assert grants_route.call_count == 2   # re-read immediately after revocation
    claims = jwt.decode(seen["jwt"], options={"verify_signature": False})
    assert claims["establishment_id"] == "EST-1" and claims["grants"] == ["ecr.prepare"]


@pytest.mark.asyncio
async def test_revoked_subject_is_denied(client):
    http, app, redis = client
    sid, _ = await login_as(app, "member")
    await redis.set("revoked:subject:test-subject", "1", ex=300)
    response = await http.get("/api/v1/members/me", cookies={"__Host-epfo-session": sid})
    assert response.status_code == 401
    assert response.json()["type"] == "/problems/revoked"


@pytest.mark.asyncio
async def test_redis_failure_fails_closed(client, monkeypatch):
    http, app, _ = client
    sid, _ = await login_as(app, "member")

    async def broken(*args, **kwargs):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(app.state.redis, "exists", broken)
    response = await http.get("/api/v1/members/me", cookies={"__Host-epfo-session": sid})
    assert response.status_code == 503
    assert response.json()["type"] == "/problems/revocation-unavailable"


@pytest.mark.asyncio
async def test_internal_token_has_owner_audience_and_short_exp_and_strips_actor_headers(client):
    http, app, _ = client
    sid, _ = await login_as(app, "member")
    jwks = (await http.get("/internal/jwks")).json()
    with respx.mock(assert_all_called=True) as router:
        upstream = router.get("http://member-service:8000/api/v1/members/me").mock(return_value=Response(200, json={"data": {}}))
        response = await http.get("/api/v1/members/me", cookies={"__Host-epfo-session": sid},
                                  headers={"X-Actor-Id": "attacker", "X-Actor-Role": "ho.security",
                                           "X-Actor-Arbitrary": "spoofed", "Authorization": "Bearer forged"})
    assert response.status_code == 200
    assert len(response.headers["x-correlation-id"]) == 36
    request = upstream.calls[0].request
    assert not any(name.startswith("x-actor-") for name in request.headers)
    claims = jwt.decode(request.headers["authorization"].split()[1], PyJWK.from_dict(jwks["keys"][0]).key,
                        algorithms=["EdDSA"], audience="member-service", issuer="epfo-gateway")
    assert claims["aud"] == "member-service"
    assert claims["exp"] - claims["iat"] <= 60


@pytest.mark.asyncio
async def test_revocation_persisted_before_success_is_returned(client):
    http, app, redis = client
    sid, session = await login_as(app, "employer.owner")
    route = next(r for r in app.state.routes if r["path_template"] == "/employers/me/operators/{operatorId}/revocations")
    route["step_up"] = False  # step-up is covered by its own tests; this test isolates the revocation write
    event = {"data": {"revocation": {"subject": "target-subject", "establishment_id": "EST-1",
                                      "grant_id": "grant-1", "scope": "grant"}}}
    with respx.mock(assert_all_called=True) as router:
        router.get(url__regex=r"http://employer-service:8000/internal/actors/.*/grants").mock(
            return_value=Response(200, json={"data": {"establishments": [{"establishment_id": "EST-1", "grants": ["operators.manage"]}]}}))
        upstream = router.post("http://employer-service:8000/api/v1/employers/me/operators/op-1/revocations")
        async def reply(request):
            return Response(200, json=event)
        upstream.mock(side_effect=reply)
        response = await http.post("/api/v1/employers/me/operators/op-1/revocations",
            cookies={"__Host-epfo-session": sid, "epfo-csrf": session["csrf"]},
            headers={"X-CSRF-Token": session["csrf"]})
    assert response.status_code == 200
    assert await redis.exists("revoked:grant:target-subject:EST-1:grant-1")


@pytest.mark.asyncio
async def test_permissions_route_returns_only_callers_grants(client):
    http, app, _ = client
    sid, _ = await login_as(app, "ho.security")
    response = await http.get("/api/v1/security/me/permissions", cookies={"__Host-epfo-session": sid})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source"] == "synthetic-poc"  # standard envelope (init.md §3.2)
    result = body["data"]
    assert result["stakeholder"] == "ho.security"
    assert result["endpoints"]
    def callers(g):
        method, path = g["endpoint"].split(" ", 1)
        return next(r for r in app.state.routes if r["method"] == method and r["path_template"] == path)["callers"]
    assert all("ho.security" in callers(g) or "*" in callers(g) for g in result["endpoints"])


@pytest.mark.asyncio
async def test_self_permissions_route_open_to_every_authenticated_stakeholder(client):
    http, app, _ = client
    sid, _ = await login_as(app, "member")
    response = await http.get("/api/v1/security/me/permissions", cookies={"__Host-epfo-session": sid})
    assert response.status_code == 200 and response.json()["data"]["stakeholder"] == "member"


def test_key_id_is_a_thumbprint_that_changes_with_the_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as K

    from app.internal_jwt import key_id, public_jwks
    a, b = K.generate(), K.generate()
    assert key_id(a) != key_id(b)
    assert public_jwks(a)["keys"][0]["kid"] == key_id(a)


@pytest.mark.asyncio
async def test_oidc_code_callback_uses_pkce_and_validates_keycloak_jwks(client):
    http, app, redis = client
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    with respx.mock(assert_all_called=True) as router:
        router.get("https://keycloak.example/realms/epfo-demo/protocol/openid-connect/certs").mock(
            return_value=Response(200, json={"keys": [jwk]}))
        token_exchange = router.post("https://keycloak.example/realms/epfo-demo/protocol/openid-connect/token")
        login = await http.get("/auth/login", params={"persona": "member-a", "return_to": "/demo"})
        assert login.status_code == 302
        from urllib.parse import parse_qs, urlparse
        auth_params = parse_qs(urlparse(login.headers["location"]).query)
        assert auth_params["login_hint"] == ["member-a"]
        assert auth_params["code_challenge_method"] == ["S256"]
        state = auth_params["state"][0]
        saved = json.loads(await redis.get(f"oidc:state:{state}"))
        now = int(time.time())
        base = {"iss": "https://keycloak.example/realms/epfo-demo", "sub": "oidc-member",
                "iat": now, "exp": now + 300}
        identity = jwt.encode({**base, "aud": "epfo-bff", "nonce": saved["nonce"],
                               "name": "Synthetic Member"}, private_key, algorithm="RS256", headers={"kid": "test-key"})
        access = jwt.encode({**base, "azp": "epfo-bff", "realm_access": {"roles": ["member"]}}, private_key,
                            algorithm="RS256", headers={"kid": "test-key"})
        token_exchange.mock(return_value=Response(200, json={"id_token": identity, "access_token": access,
            "refresh_token": "refresh-secret", "expires_in": 300}))
        callback = await http.get("/auth/callback", params={"code": "authorization-code", "state": state})
    assert callback.status_code == 303
    assert callback.headers["location"] == "/demo"
    cookie = callback.headers["set-cookie"]
    assert "__Host-epfo-session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "epfo-csrf=" in cookie
    assert await redis.get(f"oidc:state:{state}") is None


@pytest.mark.asyncio
async def test_oidc_callback_rejects_access_token_issued_to_another_client(client):
    http, app, redis = client
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": "test-key-2", "use": "sig", "alg": "RS256"})
    with respx.mock() as router:
        router.get("https://keycloak.example/realms/epfo-demo/protocol/openid-connect/certs").mock(
            return_value=Response(200, json={"keys": [jwk]}))
        token_exchange = router.post("https://keycloak.example/realms/epfo-demo/protocol/openid-connect/token")
        login = await http.get("/auth/login", params={"persona": "member-a", "return_to": "/"})
        from urllib.parse import parse_qs, urlparse
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
        saved = json.loads(await redis.get(f"oidc:state:{state}"))
        now = int(time.time())
        base = {"iss": "https://keycloak.example/realms/epfo-demo", "sub": "oidc-member", "iat": now, "exp": now + 300}
        identity = jwt.encode({**base, "aud": "epfo-bff", "nonce": saved["nonce"]}, private_key, algorithm="RS256",
                              headers={"kid": "test-key-2"})
        access = jwt.encode({**base, "azp": "some-other-client", "realm_access": {"roles": ["member"]}}, private_key,
                            algorithm="RS256", headers={"kid": "test-key-2"})
        token_exchange.mock(return_value=Response(200, json={"id_token": identity, "access_token": access,
                                                             "refresh_token": "r", "expires_in": 300}))
        callback = await http.get("/auth/callback", params={"code": "c", "state": state})
    assert callback.status_code == 401
    assert "set-cookie" not in callback.headers


def test_backchannel_uses_internal_keycloak_url_but_keeps_public_issuer():
    from types import SimpleNamespace

    from app.oidc import _backchannel, _issuer
    settings = SimpleNamespace(keycloak_issuer="http://localhost:8080/realms/epfo-demo",
                               keycloak_internal_url="http://keycloak:8080")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    assert _issuer(request) == "http://localhost:8080/realms/epfo-demo"
    assert _backchannel(request) == "http://keycloak:8080/realms/epfo-demo"


@pytest.mark.asyncio
async def test_phase_2_mock_route_answers_planned_not_502(client):
    http, app, _ = client
    sid, session = await login_as(app, "member")
    response = await http.post("/api/v1/members/uan-activations",
                               cookies={"__Host-epfo-session": sid, "epfo-csrf": session["csrf"]},
                               headers={"X-CSRF-Token": session["csrf"]})
    assert response.status_code == 501
    assert response.json()["type"] == "/problems/planned"
