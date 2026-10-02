import hashlib
import hmac
import httpx
import pytest

from app.main import app
from app.api.routes import _sms_messages, _email_messages

from app.config import settings


def signed(path):
    return {"X-Signature": hmac.new(settings.mock_gateway_secret.encode(), path.encode(), hashlib.sha256).hexdigest()}


def test_gateway_history_is_bounded():
    assert _sms_messages.maxlen == _email_messages.maxlen == 200


@pytest.mark.asyncio
async def test_sms_signature_delivery_and_list(monkeypatch):
    monkeypatch.delenv("MOCK_SMS_DOWN", raising=False)
    path = "/mock-sms/messages"
    body = {"to": "******1234", "sender_id": "EPFOHO", "template_key": "CLAIM_SETTLED",
            "text": "EPFO: Paid", "reference": "REF-1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(path, json=body)).status_code == 401
        result = await client.post(path, headers=signed(path), json=body)
        assert result.status_code == 202 and result.json()["status"] == "DELIVERED"
        assert any(row["message_id"] == result.json()["message_id"] for row in (await client.get(path, headers=signed(path))).json())
        assert (await client.get(path)).status_code == 401
        assert (await client.post(path, headers=signed(path), json={**body, "to": ""})).json()["status"] == "INVALID_NUMBER"
        monkeypatch.setenv("MOCK_SMS_DOWN", "1")
        assert (await client.post(path, headers=signed(path), json=body)).status_code == 503


@pytest.mark.asyncio
async def test_email_bounce_down_and_list(monkeypatch):
    monkeypatch.delenv("MOCK_EMAIL_DOWN", raising=False)
    path = "/mock-email/messages"
    body = {"to": "masked@example.invalid", "subject": "Notice", "body": "Body", "reference": "REF-2"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, headers=signed(path), json=body)
        assert response.status_code == 202 and response.json()["status"] == "DELIVERED"
        assert (await client.get(path, headers=signed(path))).json()[-1]["message_id"] == response.json()["message_id"]
        bounce = await client.post(path, headers=signed(path), json={**body, "to": "x@bounce.invalid"})
        assert bounce.status_code == 422 and bounce.json() == {"status": "BOUNCED"}
        monkeypatch.setenv("MOCK_EMAIL_DOWN", "1")
        assert (await client.post(path, headers=signed(path), json=body)).status_code == 503
