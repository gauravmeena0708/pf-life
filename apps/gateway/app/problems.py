from fastapi.responses import JSONResponse


def problem(request, status: int, kind: str, title: str, detail: str | None = None):
    body = {"type": f"/problems/{kind}", "title": title, "status": status,
            "correlation_id": getattr(request.state, "correlation_id", "")}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type="application/problem+json")
