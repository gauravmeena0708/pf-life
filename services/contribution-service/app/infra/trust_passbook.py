"""Signed, cached read of an exempted trust's member passbook."""
import asyncio
import hashlib
import hmac
import json
from datetime import UTC, date, datetime, timedelta
from urllib.request import Request, urlopen

from sqlalchemy import text

from app.config import settings
from epfo_persistence.policy import rules_on, section


async def _fetch_trust(trust_id: str, account: str) -> dict:
    path = f"/mock-trust/{trust_id}/members/{account}/passbook"
    signature = hmac.new(settings.mock_trust_api_secret.encode(), path.encode(), hashlib.sha256).hexdigest()

    def get():
        request = Request(settings.trust_base_url.rstrip("/") + path, headers={"X-Signature": signature})
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    return await asyncio.to_thread(get)


async def trust_section(session, account: str, exemption: dict) -> dict:
    cached = (await session.execute(text("SELECT payload,fetched_at FROM trust_passbook_cache WHERE account_link_id=:a"),
                                    {"a": account})).mappings().first()
    rules = await rules_on(session, date.today())
    minutes = section(rules, "exempted_establishments")["passbook_cache_minutes"]
    now = datetime.now(UTC)

    def render(payload, fetched, stale):
        value = payload if isinstance(payload, dict) else json.loads(payload)
        balance = value.get("balance") or {"employee_paise": value.get("employee_paise", 0),
                                           "employer_paise": value.get("employer_paise", 0)}
        return {"source": exemption["trust_name"], "fetched_at": fetched.isoformat(), "stale": stale,
                "balance": balance, "entries": value.get("entries", []), "service_from": value.get("service_from"),
                "service_to": value.get("service_to"), "note": "As reported by the trust"}

    fetched = cached["fetched_at"] if cached else None
    if isinstance(fetched, str):
        fetched = datetime.fromisoformat(fetched)
    if fetched and fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    if cached and now - fetched < timedelta(minutes=minutes):
        return render(cached["payload"], fetched, False)
    try:
        payload = await _fetch_trust(exemption["trust_id"], account)
        await session.execute(text("""INSERT INTO trust_passbook_cache (account_link_id,payload,fetched_at)
            VALUES (:a,:p,:at) ON CONFLICT (account_link_id) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at"""),
            {"a": account, "p": json.dumps(payload), "at": now})
        await session.commit()
        return render(payload, now, False)
    except (OSError, ValueError, TimeoutError):
        if cached:
            return render(cached["payload"], fetched, True)
        return {"unavailable": True, "contact": exemption["trust_name"]}
