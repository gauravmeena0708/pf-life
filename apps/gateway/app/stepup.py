"""Step-up confirmation (init.md §6.3, architecture §5.6).

A challenge states exactly what is being authorised; the demo OTP is shown to the user (a labelled
SIMULATION of a second factor). Verifying it yields a single-use token bound to subject, action,
resource, version and amount, valid for 5 minutes. The gateway consumes the token on the protected
request and passes the binding to the owning service, which checks that it matches the resource.
"""
import hashlib
import json
import secrets
import time

from fastapi import Request

from .problems import problem

TTL_SECONDS = 300
MAX_ATTEMPTS = 3


def _hash(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


async def create_challenge(request: Request, principal: dict) -> dict | object:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not body.get("action") or not body.get("resource_id") or not body.get("summary"):
        return problem(request, 400, "validation", "Step-up needs action, resource_id and summary",
                       "Say exactly what the user is confirming.")
    challenge_id, otp = secrets.token_urlsafe(16), f"{secrets.randbelow(10**6):06d}"
    record = {"subject": principal["subject"], "action": str(body["action"]), "resource_id": str(body["resource_id"]),
              "resource_version": body.get("resource_version"), "amount_paise": body.get("amount_paise"),
              "summary": str(body["summary"])[:500], "otp": _hash(otp), "attempts": 0}
    await request.app.state.redis.setex(f"stepup:challenge:{challenge_id}", TTL_SECONDS, json.dumps(record))
    return {"data": {"challenge_id": challenge_id, "expires_in_seconds": TTL_SECONDS, "summary": record["summary"],
                     "demo_otp": otp, "demo_notice": "SIMULATED second factor: in a real system this code is sent to "
                                                     "the registered mobile or produced by an authenticator."}}


async def verify_challenge(request: Request, principal: dict, challenge_id: str) -> dict | object:
    key = f"stepup:challenge:{challenge_id}"
    raw = await request.app.state.redis.get(key)
    record = json.loads(raw) if raw else None
    if not record or record["subject"] != principal["subject"]:
        return problem(request, 404, "not-found", "Confirmation expired or not found", "Start the confirmation again.")
    try:
        otp = str((await request.json()).get("otp", ""))
    except (ValueError, AttributeError):
        otp = ""
    if not secrets.compare_digest(_hash(otp), record["otp"]):
        record["attempts"] += 1
        if record["attempts"] >= MAX_ATTEMPTS:
            await request.app.state.redis.delete(key)
            return problem(request, 403, "step-up-failed", "Too many wrong codes", "Start the confirmation again.")
        await request.app.state.redis.setex(key, TTL_SECONDS, json.dumps(record))
        return problem(request, 403, "step-up-failed", "The code is not correct",
                       f"{MAX_ATTEMPTS - record['attempts']} attempt(s) left.")
    await request.app.state.redis.delete(key)
    token = secrets.token_urlsafe(24)
    binding = {k: record[k] for k in ("subject", "action", "resource_id", "resource_version", "amount_paise")}
    binding["confirmed_at"] = int(time.time())
    await request.app.state.redis.setex(f"stepup:token:{token}", TTL_SECONDS, json.dumps(binding))
    return {"data": {"step_up_token": token, "expires_in_seconds": TTL_SECONDS}}


async def consume_token(request: Request, principal: dict, token: str) -> dict | None:
    """Single use: the token is deleted on first read. Returns the binding or None."""
    redis = request.app.state.redis
    key = f"stepup:token:{token}"
    raw = await redis.getdel(key) if hasattr(redis, "getdel") else None
    if raw is None and not hasattr(redis, "getdel"):
        raw = await redis.get(key)
        await redis.delete(key)
    if not raw:
        return None
    binding = json.loads(raw)
    if binding.get("subject") != principal["subject"]:
        return None
    return {k: binding[k] for k in ("action", "resource_id", "resource_version", "amount_paise")}
