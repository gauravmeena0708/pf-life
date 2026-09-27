import json
import os
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Point the service at an unreachable database: slice-1 tests must not need Docker.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nobody:none@127.0.0.1:1/none")

KEY = Ed25519PrivateKey.generate()
KID = "test-key"
JWKS = {"keys": [{**json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(KEY.public_key())), "kid": KID}]}


@pytest.fixture
def client():
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    epfo_auth.configure(audience="{{SERVICE_NAME}}", jwks=epfo_auth.JwksCache("http://test", fetch=lambda _: JWKS))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def internal_token():
    def make(stakeholder: str = "member", audience: str = "{{SERVICE_NAME}}") -> str:
        now = int(time.time())
        claims = {"iss": "epfo-gateway", "aud": audience, "sub": "subject-1", "stakeholder": stakeholder,
                  "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
        return jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})
    return make
