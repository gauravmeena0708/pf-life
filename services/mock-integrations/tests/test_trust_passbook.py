"""The synthetic exempted trust exposes only signed, scoped passbook reads."""
import hashlib
import hmac
import json
from datetime import date
from pathlib import Path

from app.config import settings

SEED_FILE = Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json"
TRUST_ID = "TRUST-DEMO-0004"
ACCOUNT_ID = "AL-0915"


def _path(trust_id=TRUST_ID, account_link_id=ACCOUNT_ID):
    return f"/mock-trust/{trust_id}/members/{account_link_id}/passbook"


def _signed_get(client, path):
    signature = hmac.new(settings.mock_trust_api_secret.encode(), path.encode(), hashlib.sha256).hexdigest()
    return client.get(path, headers={"X-Signature": signature})


def test_signed_passbook(client, monkeypatch):
    monkeypatch.setenv("SEED_FILE", str(SEED_FILE))
    monkeypatch.delenv("MOCK_TRUST_DOWN", raising=False)
    account = json.loads(SEED_FILE.read_text(encoding="utf-8"))["trust_ledgers"]["accounts"][0]

    response = _signed_get(client, _path())

    assert response.status_code == 200
    assert response.json() == {
        "trust_id": TRUST_ID, "account_link_id": ACCOUNT_ID, "uan_masked": "********0911",
        "employee_paise": account["employee_paise"], "employer_paise": account["employer_paise"],
        "service_from": account["service_from"], "service_to": account["service_to"],
        "breaks_months": account["breaks_months"], "entries": account["entries"], "as_of": date.today().isoformat(),
    }


def test_bad_or_missing_signature(client):
    path = _path()
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Signature": "wrong"}).status_code == 401


def test_unknown_trust_or_account(client, monkeypatch):
    monkeypatch.setenv("SEED_FILE", str(SEED_FILE))
    monkeypatch.delenv("MOCK_TRUST_DOWN", raising=False)
    assert _signed_get(client, _path(account_link_id="AL-UNKNOWN")).status_code == 404
    assert _signed_get(client, _path(trust_id="TRUST-UNKNOWN")).status_code == 404


def test_trust_down_switch(client, monkeypatch):
    monkeypatch.setenv("MOCK_TRUST_DOWN", "1")
    assert _signed_get(client, _path()).status_code == 503
