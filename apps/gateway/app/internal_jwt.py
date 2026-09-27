import base64
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


def public_jwks(key: Ed25519PrivateKey) -> dict:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"keys": [{"kty": "OKP", "crv": "Ed25519", "use": "sig", "alg": "EdDSA",
                      "kid": "gateway-ephemeral", "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode()}]}


def mint(key: Ed25519PrivateKey, subject: str, stakeholder: str, audience: str, correlation_id: str,
         establishment_id: str | None = None) -> str:
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": audience, "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": correlation_id,
              "kid": "gateway-ephemeral"}
    if establishment_id:
        claims["establishment_id"] = establishment_id
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": "gateway-ephemeral"})
