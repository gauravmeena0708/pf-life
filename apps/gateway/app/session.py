import json
import secrets
import time

from cryptography.fernet import Fernet


class SessionStore:
    def __init__(self, redis, fernet: Fernet, idle_seconds: int = 1800, max_seconds: int = 28800):
        self.redis, self.fernet = redis, fernet
        self.idle_seconds, self.max_seconds = idle_seconds, max_seconds

    async def create(self, session: dict) -> tuple[str, dict]:
        sid = secrets.token_urlsafe(32)
        now = int(time.time())
        session.update({"created_at": now, "last_seen": now, "csrf": secrets.token_urlsafe(32)})
        ttl = min(self.idle_seconds, self.max_seconds)
        await self.redis.setex(self.key(sid), ttl, self.fernet.encrypt(json.dumps(session).encode()))
        return sid, session

    @staticmethod
    def key(sid: str) -> str:
        return f"session:{sid}"

    async def get(self, sid: str) -> dict | None:
        raw = await self.redis.get(self.key(sid))
        if not raw:
            return None
        session = json.loads(self.fernet.decrypt(raw).decode())
        now = int(time.time())
        if now - session["created_at"] >= self.max_seconds or now - session["last_seen"] >= self.idle_seconds:
            await self.delete(sid)
            return None
        session["last_seen"] = now
        ttl = min(self.idle_seconds, self.max_seconds - (now - session["created_at"]))
        await self.redis.setex(self.key(sid), max(1, ttl), self.fernet.encrypt(json.dumps(session).encode()))
        return session

    async def update(self, sid: str, session: dict) -> None:
        now = int(time.time())
        ttl = min(self.idle_seconds, max(1, self.max_seconds - (now - session["created_at"])))
        session["last_seen"] = now
        await self.redis.setex(self.key(sid), ttl, self.fernet.encrypt(json.dumps(session).encode()))

    async def delete(self, sid: str) -> None:
        await self.redis.delete(self.key(sid))
