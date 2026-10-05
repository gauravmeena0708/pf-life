"""Consent checks for the small, explicit representative route allowlist."""
from datetime import UTC, datetime
import time

from .internal_jwt import mint

SCOPE_ROUTES = {
    "VIEW_PROFILE": {("GET", "/members/me")},
    "VIEW_PASSBOOK": {("GET", "/members/me/passbook"), ("GET", "/members/me/accounts/{accountLinkId}/passbook")},
    "VIEW_CLAIMS": {("GET", "/members/me/claims")},
    "VIEW_SERVICE_HISTORY": {("GET", "/members/me/service-history")},
    "TRACK_GRIEVANCES": {("GET", "/members/me/grievances")},
    "RAISE_GRIEVANCE": {("POST", "/members/me/grievances")},
}

CACHE_SECONDS = 5
_cache: dict[str, tuple[float, list[dict]]] = {}


def forget(subject: str | None = None) -> None:
    if subject is None:
        _cache.clear()
    else:
        _cache.pop(subject, None)


async def grants_for(request, subject: str) -> list[dict]:
    cached = _cache.get(subject)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    token = mint(request.app.state.signing_key, "gateway", "system.gateway", "member-service",
                 request.state.correlation_id)
    response = await request.app.state.http_client.get(
        f"http://member-service:8000/internal/representatives/{subject}/grants",
        headers={"Authorization": f"Bearer {token}", "X-Correlation-Id": request.state.correlation_id}, timeout=5)
    response.raise_for_status()
    grants = response.json()["data"]["grants"]
    _cache[subject] = (time.monotonic(), grants)
    return grants


async def resolve(request, principal: dict, route: dict) -> dict | None:
    grant_id = request.headers.get("x-acting-for", "")
    if not grant_id or route["step_up"]:
        return None
    grants = await grants_for(request, principal["subject"])
    today = datetime.now(UTC).date()
    for grant in grants:
        if (grant.get("grant_id") == grant_id and grant.get("state") == "ACTIVE"
                and grant.get("valid_until", "") >= today.isoformat()
                and grant.get("member_subject") and grant.get("relation") in {"GUARDIAN", "AGENT"}):
            allowed = set().union(*(SCOPE_ROUTES.get(scope, set()) for scope in grant.get("scopes", [])))
            if (request.method.upper(), route["path_template"]) in allowed:
                return grant
    return None
