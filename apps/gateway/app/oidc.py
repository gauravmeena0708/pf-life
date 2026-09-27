import base64
import hashlib
import json
import re
import secrets
from urllib.parse import parse_qs, urlencode

import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from jwt import PyJWK

from .problems import problem
from .security_events import device_hash, ensure_device_cookie, on_login
from .session import SessionStore

router = APIRouter()


def _issuer(request: Request) -> str:
    """Public issuer: used for browser redirects and for validating `iss`."""
    return request.app.state.settings.keycloak_issuer.rstrip("/")


def _backchannel(request: Request) -> str:
    """Issuer URL as reachable from the gateway (inside Docker: http://keycloak:8080/realms/...)."""
    settings = request.app.state.settings
    issuer = settings.keycloak_issuer.rstrip("/")
    if not settings.keycloak_internal_url:
        return issuer
    realm_path = "/realms/" + issuer.split("/realms/", 1)[1]
    return settings.keycloak_internal_url.rstrip("/") + realm_path


_JWKS_TTL_SECONDS = 300
_jwks_cache: dict[str, tuple[float, list[dict]]] = {}


async def _jwks(request: Request, kid: str | None) -> list[dict]:
    url = f"{_backchannel(request)}/protocol/openid-connect/certs"
    cached = _jwks_cache.get(url)
    fresh = cached and __import__("time").monotonic() - cached[0] < _JWKS_TTL_SECONDS
    if fresh and any(k.get("kid") == kid for k in cached[1]):
        return cached[1]
    async with httpx.AsyncClient(timeout=5) as client:  # unknown kid or stale cache: refetch (key rotation)
        response = await client.get(url)
        response.raise_for_status()
    keys = response.json().get("keys", [])
    _jwks_cache[url] = (__import__("time").monotonic(), keys)
    return keys


async def verify_token(request: Request, token: str, *, audience: str | None = None) -> dict:
    issuer = _issuer(request)
    header = jwt.get_unverified_header(token)
    jwk = next((key for key in await _jwks(request, header.get("kid")) if key.get("kid") == header.get("kid")), None)
    if not jwk:
        raise ValueError("unknown signing key")
    public_key = PyJWK.from_dict(jwk).key
    options = {"verify_aud": audience is not None}
    return jwt.decode(token, public_key, algorithms=["RS256", "RS384", "RS512", "PS256", "ES256", "EdDSA"], issuer=issuer,
                      audience=audience, options=options)


def _session_store(request: Request) -> SessionStore:
    return request.app.state.sessions


@router.get("/auth/login")
async def login(request: Request, persona: str, return_to: str = "/"):
    if not _safe_return_to(return_to):
        return problem(request, 400, "invalid-return-to", "Invalid return path")
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    payload = json.dumps({"nonce": nonce, "verifier": verifier, "return_to": return_to})
    await request.app.state.redis.setex(f"oidc:state:{state}", 300, payload)
    params = {"client_id": request.app.state.settings.keycloak_client_id, "response_type": "code",
              "scope": "openid profile", "redirect_uri": f"{request.app.state.settings.gateway_public_origin.rstrip('/')}/auth/callback",
              "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
              "login_hint": persona}
    return RedirectResponse(f"{_issuer(request)}/protocol/openid-connect/auth?{urlencode(params)}", status_code=302)


def _safe_return_to(path: str) -> bool:
    return path.startswith("/") and not path.startswith("//") and "\\" not in path


@router.get("/auth/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error or not code or not state:
        return problem(request, 400, "oidc-callback", "OIDC sign-in failed")
    state_key = f"oidc:state:{state}"
    saved = await request.app.state.redis.get(state_key)
    await request.app.state.redis.delete(state_key)
    if not saved:
        return problem(request, 400, "oidc-state", "Invalid or expired sign-in state")
    saved = json.loads(saved)
    settings = request.app.state.settings
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{_backchannel(request)}/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "client_id": settings.keycloak_client_id,
            "client_secret": settings.keycloak_client_secret, "code": code,
            "redirect_uri": f"{settings.gateway_public_origin.rstrip('/')}/auth/callback",
            "code_verifier": saved["verifier"],
        })
    if response.status_code != 200:
        return problem(request, 401, "oidc-token", "Sign-in token exchange failed")
    tokens = response.json()
    try:
        identity = await verify_token(request, tokens["id_token"], audience=settings.keycloak_client_id)
        access = await verify_token(request, tokens["access_token"])
        if identity.get("nonce") != saved["nonce"] or identity.get("sub") != access.get("sub"):
            raise ValueError("OIDC identity mismatch")
        if access.get("azp") != settings.keycloak_client_id:  # token must have been issued to this BFF client
            raise ValueError("OIDC identity mismatch")
        stakeholder = request.app.state.stakeholder_for_claims(access)
        if not stakeholder:
            raise ValueError("no recognized stakeholder realm role")
    except Exception:
        return problem(request, 401, "oidc-token", "Sign-in token validation failed")
    from time import time
    session = {"tokens": tokens, "subject": access["sub"], "stakeholder": stakeholder,
               "persona_label": identity.get("name") or identity.get("preferred_username") or stakeholder,
               "expires_at": int(time()) + int(tokens.get("expires_in", 300)),
               "issuer": _issuer(request)}
    response = RedirectResponse(saved["return_to"], status_code=303)
    session["device"] = device_hash(request, ensure_device_cookie(request, response))
    sid, saved_session = await _session_store(request).create(session)
    await on_login(request, sid, saved_session)
    response.set_cookie("__Host-epfo-session", sid, httponly=True, secure=True, samesite="strict", path="/")
    response.set_cookie("epfo-csrf", saved_session["csrf"], httponly=False, secure=True, samesite="strict", path="/")
    return response


async def session_context(request: Request, *, refresh: bool = True):
    sid = request.cookies.get("__Host-epfo-session")
    if not sid:
        return None, None
    session = await _session_store(request).get(sid)
    if not session:
        return sid, None
    tokens = session["tokens"]
    if refresh and session["expires_at"] <= int(__import__("time").time()) + 60:
        settings = request.app.state.settings
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{_backchannel(request)}/protocol/openid-connect/token", data={
                "grant_type": "refresh_token", "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret, "refresh_token": tokens["refresh_token"],
            })
        if response.status_code != 200:
            await _session_store(request).delete(sid)
            return sid, None
        rotated = response.json()
        try:
            access = await verify_token(request, rotated["access_token"])
            if rotated.get("id_token"):
                refreshed_identity = await verify_token(request, rotated["id_token"], audience=settings.keycloak_client_id)
                if refreshed_identity.get("sub") != session["subject"]:
                    raise ValueError("refreshed identity mismatch")
            stakeholder = request.app.state.stakeholder_for_claims(access)
            if access.get("sub") != session["subject"] or not stakeholder:
                raise ValueError("refreshed identity mismatch")
        except Exception:
            await _session_store(request).delete(sid)
            return sid, None
        session["tokens"] = {**tokens, **rotated}
        session["expires_at"] = int(__import__("time").time()) + int(rotated.get("expires_in", 300))
        session["stakeholder"] = stakeholder
        await _session_store(request).update(sid, session)
    return sid, session


@router.get("/auth/session")
async def get_session(request: Request):
    try:
        sid, session = await session_context(request)
    except Exception:
        return {"authenticated": False}
    if not session:
        return {"authenticated": False}
    request.state.actor_subject = session["subject"]
    request.state.actor_stakeholder = session["stakeholder"]
    return {"authenticated": True, "subject": session["subject"], "stakeholder": session["stakeholder"],
            "persona_label": session["persona_label"], "expires_at": session["expires_at"]}


@router.post("/auth/logout")
async def logout(request: Request, next_persona: str | None = None, return_to: str = "/"):
    if next_persona and (not re.fullmatch(r"[a-z0-9-]{1,64}", next_persona) or not _safe_return_to(return_to)):
        return problem(request, 400, "invalid-return-to", "Invalid sign-in destination")
    sid = request.cookies.get("__Host-epfo-session")
    csrf_header, csrf_cookie = request.headers.get("x-csrf-token"), request.cookies.get("epfo-csrf")
    if not csrf_header and request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        body = await request.body()
        if len(body) <= 4096:
            csrf_header = parse_qs(body.decode("utf-8", errors="replace")).get("csrf_token", [None])[0]
    if sid and (not csrf_header or not csrf_cookie or not secrets.compare_digest(csrf_header, csrf_cookie)):
        return problem(request, 403, "csrf", "CSRF token missing or invalid")
    id_token = None
    if sid:
        session = await _session_store(request).get(sid)
        if session:
            request.state.actor_subject = session["subject"]
            request.state.actor_stakeholder = session["stakeholder"]
            id_token = session["tokens"].get("id_token")
        await _session_store(request).delete(sid)
    settings = request.app.state.settings
    origin = settings.gateway_public_origin.rstrip("/")
    next_url = origin + "/"
    if next_persona:
        next_url = f"{origin}/auth/login?{urlencode({'persona': next_persona, 'return_to': return_to})}"
    params = {"client_id": settings.keycloak_client_id,
              "post_logout_redirect_uri": next_url}
    if id_token:
        params["id_token_hint"] = id_token
    response = RedirectResponse(f"{_issuer(request)}/protocol/openid-connect/logout?{urlencode(params)}", status_code=303)
    response.delete_cookie("__Host-epfo-session", path="/", secure=True, httponly=True, samesite="strict")
    response.delete_cookie("epfo-csrf", path="/", secure=True, samesite="strict")
    return response
