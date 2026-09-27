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
