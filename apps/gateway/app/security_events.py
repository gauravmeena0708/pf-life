"""Device recognition, security-event reporting and session inspection (Journey D, interface 17).

The browser keeps an opaque, HttpOnly `epfo-device` cookie. The gateway only ever stores and reports a
salted hash of it, so no raw device data leaves the gateway. Logins and a few sensitive member actions
are reported to audit-service, which publishes SecurityEventRecorded.v1 for the risk engine.

Session IDs are bearer secrets and never leave the gateway; sessions are shown and revoked by a
one-way handle derived from the ID."""
import asyncio
import hashlib
import json
import logging
import secrets

from fastapi import Request

from .internal_jwt import mint

log = logging.getLogger("gateway.security")
DEVICE_COOKIE = "epfo-device"
DEVICE_COOKIE_SECONDS = 365 * 24 * 3600
AUDIT_URL = "http://audit-service:8000/api/v1/internal/security-events"
# Successful member actions worth a security event (route template → event type).
SENSITIVE_ACTIONS = {
    ("PATCH", "/members/me/contact-details"): "CONTACT_DETAILS_CHANGED",
    ("POST", "/members/me/claims"): "CLAIM_CREATED",
    ("POST", "/members/me/security-reports"): "MEMBER_SECURITY_REPORT",
    ("POST", "/members/me/account-recovery-requests"): "ACCOUNT_RECOVERY_REQUESTED",
}
_pending: set[asyncio.Task] = set()


def device_hash(request: Request, device_id: str) -> str:
    salt = request.app.state.settings.device_hash_salt
    return hashlib.sha256(f"{salt}:{device_id}".encode()).hexdigest()[:32]


def handle_for(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()[:20]


def ensure_device_cookie(request: Request, response) -> str:
    """Return this browser's device ID, setting the cookie on `response` if the browser has none."""
    device_id = request.cookies.get(DEVICE_COOKIE)
    if not device_id or len(device_id) > 64:
        device_id = secrets.token_urlsafe(24)
        response.set_cookie(DEVICE_COOKIE, device_id, max_age=DEVICE_COOKIE_SECONDS, httponly=True, secure=True,
                            samesite="lax", path="/")
    return device_id


async def _post(request: Request, subject: str, event_type: str, device: str) -> None:
    token = mint(request.app.state.signing_key, "gateway", "system.gateway", "audit-service", request.state.correlation_id)
    try:
        response = await request.app.state.http_client.post(AUDIT_URL, json={
            "subject": subject, "event_type": event_type, "device_fingerprint_hash": device},
            headers={"Authorization": f"Bearer {token}", "X-Correlation-Id": request.state.correlation_id}, timeout=3)
        if response.status_code >= 300:
            log.warning("security event rejected: %s %s", event_type, response.status_code)
    except Exception:
        log.warning("security event not delivered: %s", event_type)


def report(request: Request, subject: str, event_type: str, device: str) -> None:
    """Fire and forget: a slow or unavailable audit service never blocks a login or a member action."""
    task = asyncio.create_task(_post(request, subject, event_type, device))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def on_login(request: Request, sid: str, session: dict) -> None:
    redis, subject = request.app.state.redis, session["subject"]
    await redis.sadd(f"sessions:{subject}", sid)
    await redis.sadd("sessions:all", sid)
    await redis.hset("session-handles", handle_for(sid), sid)
    new_device = not await redis.sismember(f"devices:{subject}", session["device"])
    await redis.sadd(f"devices:{subject}", session["device"])
    report(request, subject, "LOGIN_NEW_DEVICE" if new_device else "LOGIN", session["device"])


def after_action(request: Request, method: str, template: str, principal: dict) -> None:
    event_type = SENSITIVE_ACTIONS.get((method, template))
    session = principal.get("session") or {}
    if event_type and session.get("device"):
        report(request, principal["subject"], event_type, session["device"])


async def _peek(request: Request, sid: str) -> dict | None:
    """Read a session without extending it (inspection must not keep a session alive)."""
    raw = await request.app.state.redis.get(f"session:{sid}")
    return json.loads(request.app.state.sessions.fernet.decrypt(raw).decode()) if raw else None


async def list_sessions(request: Request, subject: str | None, current_sid: str | None) -> list[dict]:
    redis = request.app.state.redis
    index = f"sessions:{subject}" if subject else "sessions:all"
    out = []
    for sid in sorted(await redis.smembers(index)):
        sid = sid.decode() if isinstance(sid, bytes) else sid
        session = await _peek(request, sid)
        if not session:
            await redis.srem(index, sid)
            continue
        out.append({"session_id": handle_for(sid), "subject": session["subject"], "stakeholder": session["stakeholder"],
                    "persona_label": session.get("persona_label"), "created_at": session["created_at"],
                    "last_seen": session["last_seen"], "device": (session.get("device") or "")[:8],
                    "current": sid == current_sid})
    return sorted(out, key=lambda s: s["last_seen"], reverse=True)


async def revoke_session(request: Request, handle: str, actor_subject: str) -> dict | None:
    redis = request.app.state.redis
    sid = await redis.hget("session-handles", handle)
    if not sid:
        return None
    sid = sid.decode() if isinstance(sid, bytes) else sid
    session = await _peek(request, sid)
    await redis.delete(f"session:{sid}")
    await redis.hdel("session-handles", handle)
    await redis.srem("sessions:all", sid)
    if session:
        await redis.srem(f"sessions:{session['subject']}", sid)
        report(request, session["subject"], "SESSION_REVOKED", session.get("device") or "unknown-device")
    log.info("session revoked by %s", actor_subject)
    return {"session_id": handle, "revoked": True, "subject": session["subject"] if session else None}
