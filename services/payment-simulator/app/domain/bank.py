"""MOCK bank signatures (architecture §2.8, §5.7): HMAC-SHA256 over timestamp, nonce and body."""
import hashlib
import hmac
import time

REPLAY_WINDOW_SECONDS = 300


def sign(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    message = timestamp.encode() + b"." + nonce.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(secret: str, timestamp: str, nonce: str, body: bytes, signature: str, now: float | None = None) -> str | None:
    """Return None if valid, else the reason it is rejected."""
    if not (timestamp and nonce and signature):
        return "missing signature headers"
    try:
        age = abs((now or time.time()) - int(timestamp))
    except ValueError:
        return "bad timestamp"
    if age > REPLAY_WINDOW_SECONDS:
        return "timestamp outside the replay window"
    if not hmac.compare_digest(sign(secret, timestamp, nonce, body), signature):
        return "signature does not match"
    return None
