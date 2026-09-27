"""Verify the gateway's internal JWT (docs/adr/0002-internal-jwt.md) and give routes the caller.

Services must never trust `X-Actor-*` or similar plain headers. The only identity a service accepts is
this token: EdDSA-signed by the gateway, audience = this service, lifetime <= 60 s.
"""
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
import jwt
from fastapi import Depends, Request

from epfo_observability import Problem

__all__ = ["Actor", "JwksCache", "configure", "require_actor", "require_stakeholder"]

ISSUER = "epfo-gateway"
MAX_LIFETIME_SECONDS = 60
LEEWAY_SECONDS = 5


@dataclass(frozen=True)
class Actor:
    """The authenticated caller, as resolved by the gateway."""
    subject: str
    stakeholder: str
    correlation_id: str
    establishment_id: str | None = None
    step_up: dict[str, Any] | None = None
    claims: dict[str, Any] = field(default_factory=dict, repr=False)


class JwksCache:
    """Fetches the gateway JWKS and caches it; refetches once when an unknown `kid` appears."""

    def __init__(self, url: str, ttl_seconds: int = 300, fetch: Callable[[str], dict] | None = None) -> None:
        self.url, self.ttl = url, ttl_seconds
        self._fetch = fetch or (lambda u: httpx.get(u, timeout=5).raise_for_status().json())
        self._keys: dict[str, Any] = {}
        self._loaded_at = 0.0

    def _load(self) -> None:
        jwks = self._fetch(self.url)
        self._keys = {k["kid"]: jwt.PyJWK(k).key for k in jwks.get("keys", []) if k.get("kid")}
        self._loaded_at = time.monotonic()

    def key(self, kid: str) -> Any:
        if not self._keys or time.monotonic() - self._loaded_at > self.ttl:
            self._load()
        if kid not in self._keys:
            self._load()  # key rotation
        if kid not in self._keys:
            raise KeyError(kid)
        return self._keys[kid]


_state: dict[str, Any] = {}


def configure(audience: str | None = None, jwks: JwksCache | None = None) -> None:
    """Call once at startup. Defaults come from SERVICE_NAME and GATEWAY_JWKS_URL."""
    _state["audience"] = audience or os.environ["SERVICE_NAME"]
    _state["jwks"] = jwks or JwksCache(os.environ.get("GATEWAY_JWKS_URL", "http://gateway:8000/internal/jwks"))


def _unauthorised(detail: str) -> Problem:
    return Problem(401, "/problems/unauthenticated", "Authentication required", detail)


def verify(token: str) -> Actor:
    if "audience" not in _state:
        configure()
    try:
        kid = jwt.get_unverified_header(token).get("kid", "")
        key = _state["jwks"].key(kid)
        claims = jwt.decode(
            token, key, algorithms=["EdDSA"], audience=_state["audience"], issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "jti"]}, leeway=LEEWAY_SECONDS,
        )
    except (jwt.PyJWTError, KeyError, httpx.HTTPError) as exc:
        raise _unauthorised(f"Internal token rejected ({type(exc).__name__}).") from None
    if claims["exp"] - claims["iat"] > MAX_LIFETIME_SECONDS:
        raise _unauthorised("Internal token lifetime exceeds 60 seconds.")
    if not claims.get("stakeholder"):
        raise _unauthorised("Internal token has no stakeholder.")
    return Actor(
        subject=claims["sub"], stakeholder=claims["stakeholder"], correlation_id=claims.get("correlation_id", ""),
        establishment_id=claims.get("establishment_id"), step_up=claims.get("step_up"), claims=claims,
    )


async def require_actor(request: Request) -> Actor:
    """FastAPI dependency: the verified caller, or 401 Problem."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise _unauthorised("Missing internal bearer token.")
    return verify(header[7:].strip())


def require_stakeholder(*allowed: str) -> Callable[..., Any]:
    """FastAPI dependency factory: the caller must be one of `allowed` stakeholder IDs (defence in depth;
    the gateway has already checked docs/permissions.yaml)."""

    async def dependency(actor: Actor = Depends(require_actor)) -> Actor:
        if actor.stakeholder not in allowed:
            raise Problem(403, "/problems/forbidden", "Not allowed")
        return actor

    return dependency
