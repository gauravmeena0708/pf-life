"""Small, fail-closed protections for synthetic public directory and TRRN routes."""
import json
import secrets

from fastapi import Request

from .problems import problem
from .request_activity import lookup_fingerprint, summarize_body

PROTECTED = {"/public/establishments", "/public/establishments/{estId}",
             "/public/demo-challenges", "/public/trrn-status-lookups", "/public/grievances",
             "/public/grievances/status-lookups", "/public/claims/status-lookups",
             "/public/inoperative-accounts/searches"}


def _peer(request: Request) -> str:
    # Ignore forwarded headers: only the socket peer is trusted by this local demo.
    return request.client.host if request.client else "unknown"


async def limit_public(request: Request, route: dict):
    if route["path_template"] not in PROTECTED:
        return None
    peer = _peer(request)
    try:
        key = f"public:rate:{route['path_template']}:{peer}"
        count = await request.app.state.redis.incr(key)
        if count == 1:
            await request.app.state.redis.expire(key, 60)
    except Exception:
        request.state.rate_decision = "unavailable"
        return problem(request, 503, "public-access-unavailable", "Public lookup temporarily unavailable")
    ceiling = 10 if route["path_template"] in ("/public/trrn-status-lookups", "/public/grievances",
                                               "/public/grievances/status-lookups", "/public/claims/status-lookups",
                                               "/public/inoperative-accounts/searches") else 30
    if count > ceiling:
        request.state.rate_decision = "limited"
        return problem(request, 429, "rate-limited", "Too many public lookups", "Try again in a minute.")
    request.state.rate_decision = "allowed"
    return None


async def create_demo_challenge(request: Request):
    first, second = secrets.randbelow(8) + 2, secrets.randbelow(8) + 2
    challenge_id = secrets.token_urlsafe(24)
    try:
        await request.app.state.redis.setex(
            f"public:challenge:{challenge_id}", 120,
            json.dumps({"answer": first + second, "peer": _peer(request)}))
    except Exception:
        return problem(request, 503, "public-access-unavailable", "Public lookup temporarily unavailable")
    return {"data": {"challenge_id": challenge_id, "prompt": f"What is {first} + {second}?",
                     "expires_in_seconds": 120, "proof_type": "synthetic-demo"},
            "meta": {"source": "synthetic-poc", "correlation_id": request.state.correlation_id}}


async def verify_demo_challenge(request: Request):
    body_bytes = await request.body()
    summarize_body(request, body_bytes)
    limit = 16384 if request.state.route_template == "/public/grievances" else 4096   # a grievance carries its text
    if len(body_bytes) > limit:
        request.state.challenge_decision = "rejected"
        return problem(request, 413, "request-too-large", "Lookup request is too large")
    try:
        body = await request.json()
        if isinstance(body, dict) and isinstance(body.get("trrn"), str):
            request.state.lookup_fingerprint = lookup_fingerprint(request, body["trrn"])
        challenge_id = body.get("challenge_id") if isinstance(body, dict) else None
        answer = body.get("answer") if isinstance(body, dict) else None
        if not isinstance(challenge_id, str) or not 20 <= len(challenge_id) <= 64:
            raise ValueError
        if isinstance(answer, bool) or not isinstance(answer, int):
            raise ValueError
        raw = await request.app.state.redis.getdel(f"public:challenge:{challenge_id}")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        request.state.challenge_decision = "rejected"
        return problem(request, 400, "invalid-request", "Invalid lookup request")
    except Exception:
        request.state.challenge_decision = "unavailable"
        return problem(request, 503, "public-access-unavailable", "Public lookup temporarily unavailable")
    if not raw:
        request.state.challenge_decision = "rejected"
        return problem(request, 403, "demo-proof-invalid", "Demo challenge expired or already used")
    saved = json.loads(raw)
    if saved["peer"] != _peer(request) or saved["answer"] != answer:
        request.state.challenge_decision = "rejected"
        return problem(request, 403, "demo-proof-invalid", "Demo challenge answer is incorrect")
    request.state.challenge_decision = "passed"
    return None
