"""Resolve employer users' domain grants from employer-service (architecture §3 step 2).

Cached per subject for up to 30 s; the cache entry is dropped the moment a grant or revocation
succeeds, so a revoked operator is denied on the next request (init.md §6.6)."""
import time

import httpx

from .internal_jwt import mint

EMPLOYER_STAKEHOLDERS = {"employer.owner", "employer.operator", "employer.signatory", "payroll_provider"}
CACHE_SECONDS = 30
_cache: dict[str, tuple[float, list[dict]]] = {}


def forget(subject: str | None = None) -> None:
    if subject is None:
        _cache.clear()
    else:
        _cache.pop(subject, None)


async def employer_context(request, principal: dict) -> tuple[str | None, list[str]]:
    """Returns (establishment_id, grants) for employer users; (None, []) otherwise."""
    if principal.get("stakeholder") not in EMPLOYER_STAKEHOLDERS:
        return None, []
    subject = principal["subject"]
    cached = _cache.get(subject)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        establishments = cached[1]
    else:
        token = mint(request.app.state.signing_key, "gateway", "system.gateway", "employer-service",
                     request.state.correlation_id)
        response = await request.app.state.http_client.get(
            f"http://employer-service:8000/internal/actors/{subject}/grants",
            headers={"Authorization": f"Bearer {token}", "X-Correlation-Id": request.state.correlation_id}, timeout=5)
        response.raise_for_status()
        establishments = response.json()["data"]["establishments"]
        _cache[subject] = (time.monotonic(), establishments)
    wanted = request.headers.get("x-establishment-id")
    if wanted:
        match = next((e for e in establishments if e["establishment_id"] == wanted), None)
        return (wanted, match["grants"]) if match else (None, [])
    if len(establishments) == 1:
        return establishments[0]["establishment_id"], establishments[0]["grants"]
    return None, []
