"""Short-lived, redacted request activity for the synthetic security workspace."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections import Counter
from datetime import UTC, datetime

from fastapi import Request

from .problems import problem

KEY = "security:request-activity:v2"
MAX_EVENTS = 2000
RETENTION_SECONDS = 24 * 60 * 60
log = logging.getLogger("gateway.request_activity")


def lookup_fingerprint(request: Request, value: str) -> str:
    """Correlate repeated demo lookups during one gateway run without storing their values."""
    return hmac.new(request.app.state.activity_hmac_key, value.strip().lower().encode(),
                    hashlib.sha256).hexdigest()[:16]


def summarize_body(request: Request, body: bytes) -> None:
    request.state.body_bytes = len(body)
    if len(body) > 4096 or "application/json" not in request.headers.get("content-type", ""):
        return
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return
    if isinstance(parsed, dict):
        request.state.body_fields = sorted(str(key)[:64] for key in parsed)[:20]


async def record_activity(request: Request, status_code: int, elapsed_ms: int) -> None:
    if not (request.url.path.startswith("/api/v1/") or request.url.path.startswith("/auth/")):
        return
    state = request.state
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "method": request.method,
        "route": getattr(state, "route_template", request.url.path if request.url.path.startswith("/auth/") else "unmatched"),
        "status": status_code,
        "duration_ms": elapsed_ms,
        "peer_ip": request.client.host if request.client else "unknown",
        "peer_kind": "gateway-socket-peer",
        "actor": getattr(state, "actor_subject", "anonymous"),
        "stakeholder": getattr(state, "actor_stakeholder", "public"),
        "acting_for": getattr(state, "acting_for", None),
        "query_fields": sorted(str(key)[:64] for key in request.query_params.keys())[:20],
        "body_fields": getattr(state, "body_fields", []),
        "body_bytes": getattr(state, "body_bytes", None),
        "lookup_fingerprint": getattr(state, "lookup_fingerprint", None),
        "search_mode": getattr(state, "search_mode", None),
        "rate_decision": getattr(state, "rate_decision", "allowed"),
        "challenge_decision": getattr(state, "challenge_decision", None),
        "correlation_id": getattr(state, "correlation_id", None),
    }
    # Redis is an ephemeral POC store. Monitoring must never break the requested API.
    try:
        redis = request.app.state.redis
        now = time.time()
        pipe = redis.pipeline(transaction=True)
        pipe.zadd(KEY, {json.dumps(entry, separators=(",", ":")): now})
        pipe.zremrangebyscore(KEY, "-inf", now - RETENTION_SECONDS)
        pipe.expire(KEY, RETENTION_SECONDS)
        await pipe.execute()
        count = await redis.zcard(KEY)
        if count > MAX_EVENTS:
            await redis.zremrangebyrank(KEY, 0, count - MAX_EVENTS - 1)
    except Exception:
        log.warning("Could not record request activity", exc_info=True)


async def get_request_activity(request: Request):
    try:
        raw = await request.app.state.redis.zrevrange(KEY, 0, MAX_EVENTS - 1)
    except Exception:
        return problem(request, 503, "activity-unavailable", "Request activity temporarily unavailable")
    entries = [json.loads(item) for item in raw]
    now = time.time()
    recent = [item for item in entries if now - datetime.fromisoformat(item["at"]).timestamp() <= 300]
    minute = [item for item in recent if now - datetime.fromisoformat(item["at"]).timestamp() <= 60]
    top_routes = Counter(item["route"] for item in recent).most_common(8)
    top_peers = Counter(item["peer_ip"] for item in recent).most_common(8)
    return {"data": {
        "window_seconds": 300,
        "retention_seconds": RETENTION_SECONDS,
        "history_limit": MAX_EVENTS,
        "gateway_peer_note": "Peer IP is the connection to this gateway; behind a proxy it may be the proxy, not a visitor.",
        "metrics": {"requests_5m": len(recent), "requests_1m": len(minute),
                    "blocked_5m": sum(item["status"] in (403, 429) for item in recent),
                    "challenge_failures_5m": sum(item["challenge_decision"] == "rejected" for item in recent),
                    "server_errors_5m": sum(item["status"] >= 500 for item in recent)},
        "top_routes": [{"route": route, "requests": count} for route, count in top_routes],
        "top_peers": [{"peer_ip": peer, "requests": count} for peer, count in top_peers],
        "events": entries[:100],
    }, "meta": {"source": "synthetic-poc", "correlation_id": request.state.correlation_id,
                "as_of": datetime.now(UTC).isoformat()}}
