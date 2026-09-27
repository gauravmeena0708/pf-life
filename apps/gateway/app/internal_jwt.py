import base64
import hashlib
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def load_signing_key(pem: str) -> Ed25519PrivateKey:
    if pem:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("GATEWAY_SIGNING_KEY_PEM must contain an Ed25519 private key")
        return key
    return Ed25519PrivateKey.generate()


def _x(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def key_id(key: Ed25519PrivateKey) -> str:
    """RFC 7638 JWK thumbprint: a new key always gets a new kid, so services refetch the JWKS after a
    gateway restart with an ephemeral key instead of verifying with a stale cached key."""
    canonical = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": _x(key)}, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()


def public_jwks(key: Ed25519PrivateKey) -> dict:
    return {"keys": [{"kty": "OKP", "crv": "Ed25519", "use": "sig", "alg": "EdDSA",
                      "kid": key_id(key), "x": _x(key)}]}


def mint(key: Ed25519PrivateKey, subject: str, stakeholder: str, audience: str, correlation_id: str,
         establishment_id: str | None = None, grants: list[str] | None = None, step_up: dict | None = None) -> str:
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": audience, "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": correlation_id}
    if establishment_id:
        claims["establishment_id"] = establishment_id
    if grants is not None:
        claims["grants"] = grants
    if step_up:
        claims["step_up"] = step_up
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": key_id(key)})
