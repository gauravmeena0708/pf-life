import json
import secrets

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from . import grants as grant_resolver
from .internal_jwt import mint
from .stepup import consume_token, create_challenge, verify_challenge
from .oidc import session_context, verify_token
from .problems import problem
from .public_access import create_demo_challenge, limit_public, verify_demo_challenge
from .revocation import is_revoked, record_revocation
from .routing import match_route

import structlog

log = structlog.get_logger("gateway.pipeline")


async def handle_api(request: Request, path: str):
    method = request.method.upper()
    route = match_route(request.app.state.routes, method, "/" + path)
    if not route:
        return problem(request, 404, "not-found", "Route not found")
    is_public = route["path_template"].startswith("/public/")
    principal = None
    sid = None

    if is_public:
        limited = await limit_public(request, route)
        if limited is not None:
            return limited

    # Public planned contracts are intentionally visible without a session.
    if (route["status"] in ("P", "?") or int(route.get("phase", 1)) > 1) and is_public:
        return planned(request, route)

    if is_public:
        principal = {"subject": "anonymous", "stakeholder": "public"}
    elif route["path_template"].startswith(("/integrations/", "/partners/", "/internal/")):
        authorization = request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            return problem(request, 401, "unauthenticated", "Authentication required")
        try:
            claims = await verify_token(request, authorization.split(None, 1)[1])
            stakeholder = request.app.state.stakeholder_for_claims(claims)
            if not stakeholder:
                return problem(request, 403, "forbidden", "Forbidden")
            principal = {"subject": claims.get("sub", claims.get("client_id", "machine")),
                         "stakeholder": stakeholder, "claims": claims}
        except Exception:
            return problem(request, 401, "unauthenticated", "Invalid machine token")
        # TODO: verify callback HMAC, timestamp, event id and replay window per architecture §5.7.
    else:
        try:
            _, session = await session_context(request)
        except Exception:
            return problem(request, 503, "session-unavailable", "Session store unavailable")
        if not session:
            return problem(request, 401, "unauthenticated", "Authentication required")
        principal = {"subject": session["subject"], "stakeholder": session["stakeholder"], "session": session}
        if method not in ("GET", "HEAD"):
            csrf_header, csrf_cookie = request.headers.get("x-csrf-token"), request.cookies.get("epfo-csrf")
            if not csrf_header or not csrf_cookie or not secrets.compare_digest(csrf_header, csrf_cookie):
                return problem(request, 403, "csrf", "CSRF token missing or invalid")

    if principal and not is_public:
        establishment_id = request.headers.get("x-establishment-id")
        grant_id = request.headers.get("x-grant-id")
        try:
            if await is_revoked(request.app.state.redis, principal["subject"], establishment_id, grant_id):
                return problem(request, 401, "revoked", "Actor access has been revoked")
        except Exception:
            return problem(request, 503, "revocation-unavailable", "Authorization state unavailable")

    # Check grants before revealing that a protected contract is planned.
    callers = route.get("callers", [])
    if not is_public and "*" not in callers and principal["stakeholder"] not in callers:
        return problem(request, 403, "forbidden", "Forbidden")

    if route["status"] in ("P", "?") or int(route.get("phase", 1)) > 1:
        return planned(request, route)
    if route["path_template"] == "/public/trrn-status-lookups":
        rejected = await verify_demo_challenge(request)
        if rejected is not None:
            return rejected
    step_up = None
    if route["step_up"]:
        supplied = request.headers.get("x-step-up-token")
        if not supplied:
            return problem(request, 428, "step-up-required", "Confirm this action first",
                           "Start a confirmation with POST /api/v1/security/step-up-challenges.")
        step_up = await consume_token(request, principal, supplied)
        if not step_up:
            return problem(request, 403, "step-up-invalid", "Confirmation expired, already used or not yours",
                           "Confirm the action again.")

    if route["owner"] == "gateway":
        if route["path_template"] == "/public/demo-challenges" and method == "GET":
            return await create_demo_challenge(request)
        if route["path_template"] == "/security/me/permissions" and method == "GET":
            grants = [g for g in request.app.state.permissions.get(principal["stakeholder"], [])]
            endpoints = [{"endpoint": g["endpoint"], "status": g["status"], "scope": g.get("scope", ""),
                          "step_up": bool(g.get("step_up", False))} for g in grants]
            return {"data": {"stakeholder": principal["stakeholder"], "endpoints": endpoints},
                    "meta": {"correlation_id": request.state.correlation_id, "api_version": "v1",
                             "source": "synthetic-poc",
                             "as_of": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()}}
        if route["path_template"] == "/security/step-up-challenges" and method == "POST":
            return await create_challenge(request, principal)
        if route["path_template"] == "/security/step-up-challenges/{challengeId}/verifications" and method == "POST":
            return await verify_challenge(request, principal, request.url.path.rstrip("/").split("/")[-2])
        return planned(request, {**route, "summary": route.get("summary") or "Gateway route not built yet"})

    service_name = route["upstream"].removeprefix("http://").removesuffix(":8000")
    establishment_id, grants = None, None
    if principal["stakeholder"] in grant_resolver.EMPLOYER_STAKEHOLDERS:
        try:
            establishment_id, grants = await grant_resolver.employer_context(request, principal)
        except Exception:
            return problem(request, 503, "grants-unavailable", "Permissions could not be checked",
                           "Try again in a moment.")
    token = mint(request.app.state.signing_key, principal["subject"], principal["stakeholder"],
                 service_name, request.state.correlation_id, establishment_id, grants, step_up)
    headers = {}
    for name, value in request.headers.items():
        lower = name.lower()
        if lower.startswith("x-actor-") or lower in {"authorization", "cookie", "host", "content-length", "x-csrf-token", "x-step-up-token"}:
            continue
        headers[name] = value
    headers["Authorization"] = f"Bearer {token}"
    headers["X-Correlation-Id"] = request.state.correlation_id
    target = route["upstream"].rstrip("/") + "/api/v1" + request.url.path.removeprefix("/api/v1")
    try:
        upstream = await request.app.state.http_client.request(method, target, params=request.query_params,
            content=await request.body(), headers=headers, timeout=10)
    except httpx.RequestError:
        return problem(request, 502, "upstream-unavailable", "Upstream service unavailable")

    if route.get("revocation") and 200 <= upstream.status_code < 300:
        try:
            data = upstream.json().get("data", {}).get("revocation")
            if not isinstance(data, dict):
                raise ValueError("revocation response has no data.revocation object")
            await record_revocation(request.app.state.redis, data)
            grant_resolver.forget(data.get("subject"))
        except Exception:
            log.exception("revocation persistence failed", extra={"correlation_id": request.state.correlation_id})
            return problem(request, 503, "revocation-unavailable", "Could not persist revocation")
    if 200 <= upstream.status_code < 300 and route["path_template"] in (
            "/employers/me/operators/invitations", "/employers/me/signatories/authorisations"):
        grant_resolver.forget()  # a new grant: next request re-reads permissions
    response_headers = {k: v for k, v in upstream.headers.items()
                        if k.lower() not in {"content-length", "transfer-encoding", "connection", "set-cookie"}}
    response_headers["X-Correlation-Id"] = request.state.correlation_id
    if upstream.status_code >= 400:
        try:
            body = upstream.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        body.update({"type": body.get("type", "/problems/upstream-error"),
                     "title": body.get("title", "Upstream request failed"),
                     "status": upstream.status_code, "correlation_id": request.state.correlation_id})
        return JSONResponse(body, status_code=upstream.status_code, headers=response_headers,
                            media_type="application/problem+json")
    return Response(content=upstream.content, status_code=upstream.status_code,
                    headers=response_headers, media_type=upstream.headers.get("content-type"))


def planned(request: Request, route: dict):
    return problem(request, 501, "planned", "Planned contract — not implemented in this POC",
                   route.get("summary", "Contract defined in the catalogue"))
