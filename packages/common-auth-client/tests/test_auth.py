import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import epfo_auth
from epfo_auth import Actor, JwksCache, require_actor, require_stakeholder
from epfo_observability import install

KEY = Ed25519PrivateKey.generate()
KID = "test-key-1"
JWKS = {"keys": [{**json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(KEY.public_key())), "kid": KID}]}


def token(**overrides) -> str:
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "claim-service", "sub": "user-1", "stakeholder": "member",
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    claims.update(overrides)
    key = overrides.pop("_key", KEY) if "_key" in overrides else KEY
    claims.pop("_key", None)
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": overrides.get("_kid", KID)})


@pytest.fixture(autouse=True)
def configured():
    epfo_auth.configure(audience="claim-service", jwks=JwksCache("http://x", fetch=lambda _: JWKS))


def client() -> TestClient:
    app = FastAPI()
    install(app, "claim-service")

    @app.get("/me")
    async def me(actor: Actor = Depends(require_actor)) -> dict:
        return {"sub": actor.subject, "stakeholder": actor.stakeholder}

    @app.get("/office-only")
    async def office(actor: Actor = Depends(require_stakeholder("fo.apfc"))) -> dict:
        return {"ok": True}

    return TestClient(app)


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_valid_token():
    r = client().get("/me", headers=auth(token()))
    assert r.status_code == 200 and r.json() == {"sub": "user-1", "stakeholder": "member"}


def test_missing_token_401():
    assert client().get("/me").status_code == 401


def test_plain_actor_headers_are_ignored():
    r = client().get("/me", headers={"X-Actor-Subject": "admin", "X-Actor-Roles": "fo.oic"})
    assert r.status_code == 401


def test_wrong_audience_401():
    assert client().get("/me", headers=auth(token(aud="member-service"))).status_code == 401


def test_wrong_issuer_401():
    assert client().get("/me", headers=auth(token(iss="someone-else"))).status_code == 401


def test_expired_401():
    now = int(time.time())
    assert client().get("/me", headers=auth(token(iat=now - 200, exp=now - 100))).status_code == 401


def test_lifetime_over_60s_401():
    now = int(time.time())
    assert client().get("/me", headers=auth(token(iat=now, exp=now + 3600))).status_code == 401


def test_other_signing_key_401():
    other = Ed25519PrivateKey.generate()
    now = int(time.time())
    forged = jwt.encode({"iss": "epfo-gateway", "aud": "claim-service", "sub": "x", "stakeholder": "fo.oic",
                         "iat": now, "exp": now + 60, "jti": "j"}, other, algorithm="EdDSA", headers={"kid": KID})
    assert client().get("/me", headers=auth(forged)).status_code == 401


def test_hs256_downgrade_rejected():
    now = int(time.time())
    forged = jwt.encode({"iss": "epfo-gateway", "aud": "claim-service", "sub": "x", "stakeholder": "fo.oic",
                         "iat": now, "exp": now + 60, "jti": "j"}, "secret", algorithm="HS256", headers={"kid": KID})
    assert client().get("/me", headers=auth(forged)).status_code == 401


def test_require_stakeholder():
    assert client().get("/office-only", headers=auth(token())).status_code == 403
    assert client().get("/office-only", headers=auth(token(stakeholder="fo.apfc"))).status_code == 200


def test_refetches_jwks_once_when_cached_key_is_stale():
    """Gateway restarted with a new key under the same kid: first verification fails, refetch succeeds."""
    new_key = Ed25519PrivateKey.generate()
    new_jwks = {"keys": [{**json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(new_key.public_key())), "kid": KID}]}
    served = [JWKS]
    cache = JwksCache("http://x", fetch=lambda _: served[0])
    epfo_auth.configure(audience="claim-service", jwks=cache)
    cache.key(KID)  # warm the cache with the old key
    served[0] = new_jwks
    now = int(time.time())
    fresh = jwt.encode({"iss": "epfo-gateway", "aud": "claim-service", "sub": "u", "stakeholder": "member",
                        "iat": now, "exp": now + 60, "jti": "j2"}, new_key, algorithm="EdDSA", headers={"kid": KID})
    assert client().get("/me", headers=auth(fresh)).status_code == 200


def test_require_grant_and_step_up():
    from epfo_auth import require_grant, require_step_up
    from epfo_observability import Problem
    a = Actor(subject="s", stakeholder="employer.signatory", correlation_id="c",
              claims={"grants": ["ecr.approve"]}, step_up={"action": "approve-ecr", "resource_id": "F1",
                                                          "resource_version": 2, "amount_paise": 500})
    require_grant(a, "ecr.approve")
    require_step_up(a, "approve-ecr", "F1", 2, 500)
    for bad in (lambda: require_grant(a, "ecr.submit"),
                lambda: require_step_up(a, "approve-ecr", "F2", 2, 500),
                lambda: require_step_up(a, "approve-ecr", "F1", 3, 500),
                lambda: require_step_up(a, "submit-ecr", "F1", 2, 500)):
        with pytest.raises(Problem):
            bad()
    with pytest.raises(Problem) as e:
        require_step_up(Actor(subject="s", stakeholder="x", correlation_id="c"), "approve-ecr", "F1")
    assert e.value.status == 428


def test_token_with_acted_by():
    acted_by_data = {"subject": "rep-1", "grant_id": "REP-123", "relation": "GUARDIAN"}
    t = token(acted_by=acted_by_data)
    actor = epfo_auth.verify(t)
    assert actor.subject == "user-1"
    assert actor.stakeholder == "member"
    assert actor.acted_by == acted_by_data

    # Default is None
    t_normal = token()
    actor_normal = epfo_auth.verify(t_normal)
    assert actor_normal.acted_by is None
