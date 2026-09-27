import sys
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[3]
GATEWAY = ROOT / "apps" / "gateway"
sys.path.insert(0, str(GATEWAY))

from app.config import Settings
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    redis = FakeRedis(decode_responses=False)
    settings = Settings(redis_url="redis://localhost", keycloak_issuer="https://keycloak.example/realms/epfo-demo",
                        keycloak_client_secret="test-secret", gateway_session_fernet_key=Fernet.generate_key().decode(),
                        gateway_public_origin="https://gateway.example")
    app = create_app(redis_client=redis, settings=settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://gateway.example") as http:
        yield http, app, redis
    await app.state.http_client.aclose()
    await redis.aclose()


async def login_as(app, role: str, subject: str = "test-subject"):
    tokens = {"access_token": "opaque-test-access", "refresh_token": "opaque-test-refresh", "id_token": "opaque-test-id"}
    sid, session = await app.state.sessions.create({"tokens": tokens, "subject": subject, "stakeholder": role,
        "persona_label": role, "expires_at": 4_000_000_000, "issuer": "https://keycloak.example/realms/epfo-demo"})
    return sid, session
