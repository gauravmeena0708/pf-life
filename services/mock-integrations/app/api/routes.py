"""Hand-written routes of mock-integrations. A real route here replaces the generated stub with the same
method and path in catalogue_routes.py."""
import hashlib
import hmac
import json
import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Header, Request

from app.config import settings
from epfo_observability import Problem

router = APIRouter()


def _trust_ledgers() -> dict:
    configured = Path(os.getenv("SEED_FILE", "/srv/seed/synthetic.json"))
    path = configured if configured.is_file() else Path(__file__).resolve().parents[4] / "scripts" / "seed" / "synthetic.json"
    with path.open(encoding="utf-8") as seed_file:
        return json.load(seed_file)["trust_ledgers"]


@router.get("/mock-trust/{trust_id}/members/{account_link_id}/passbook")
async def trust_passbook(trust_id: str, account_link_id: str, request: Request,
                         signature: str | None = Header(default=None, alias="X-Signature")) -> dict:
    """Synthetic trust passbook API, called internally with a path signature."""
    expected = hmac.new(settings.mock_trust_api_secret.encode(), request.url.path.encode(), hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise Problem(401, "/problems/bad-signature", "Trust API request rejected", "Invalid X-Signature")
    if os.getenv("MOCK_TRUST_DOWN") == "1":
        raise Problem(503, "/problems/trust-unavailable", "Trust API unavailable")

    ledgers = _trust_ledgers()
    if ledgers["trust_id"] != trust_id:
        raise Problem(404, "/problems/not-found", "Trust account not found")
    account = next((item for item in ledgers["accounts"] if item["account_link_id"] == account_link_id), None)
    if account is None:
        raise Problem(404, "/problems/not-found", "Trust account not found")
    return {"trust_id": trust_id, "account_link_id": account_link_id,
            "uan_masked": "*" * max(0, len(account["uan"]) - 4) + account["uan"][-4:],
            "employee_paise": account["employee_paise"], "employer_paise": account["employer_paise"],
            "service_from": account["service_from"], "service_to": account["service_to"],
            "breaks_months": account["breaks_months"], "entries": account["entries"], "as_of": date.today().isoformat()}
