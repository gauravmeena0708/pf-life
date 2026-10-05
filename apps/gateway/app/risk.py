"""Member request risk signals. Device identifiers are HMACs; never log the fingerprint or its inputs.

The socket peer is used for the IP prefix. Deployments behind a proxy must provide a trusted peer
address at the ASGI boundary; untrusted forwarding headers are deliberately ignored here.
"""
import hashlib
import hmac
import ipaddress


# These existing member reads disclose family or financial records, but the catalogue does not
# require confirmation on every view. Contact changes, nomination submission and transfer creation
# already require step-up and must stay governed by their fixed route flags.
SENSITIVE_ROUTES = {
    ("GET", "/members/me/nominations"),
    ("GET", "/members/me/accounts/{accountLinkId}/passbook"),
    ("GET", "/members/me/transfers/{transferId}/annexure-k"),
}
DEVICE_SECONDS = 30 * 24 * 3600
HOUR_SECONDS = 3600
FREQUENT_COUNT = 30
STEP_UP_SCORE = 2          # two signals together: a new device alone, or a busy hour alone, is not challenged


def fingerprint(request) -> str:
    ip = ipaddress.ip_address(request.client.host) if request.client else ipaddress.ip_address("0.0.0.0")
    prefix = ipaddress.ip_network(f"{ip}/24" if ip.version == 4 else f"{ip}/64", strict=False)
    material = f"{request.headers.get('user-agent', '')}|{prefix.network_address}/{prefix.prefixlen}"
    return hmac.new(request.app.state.settings.device_hash_salt.encode(), material.encode(), hashlib.sha256).hexdigest()


def binding(request, route: dict) -> tuple[str, str]:
    return f"risk:{request.method.lower()}:{route['path_template']}", request.url.path.removeprefix("/api/v1")


async def assess(request, subject: str, route: dict) -> list[str]:
    if (request.method, route["path_template"]) not in SENSITIVE_ROUTES:
        return []
    redis = request.app.state.redis
    device_key = f"risk:device:{subject}:{fingerprint(request)}"
    count_key = f"risk:count:{subject}"
    count = await redis.incr(count_key)
    if count == 1:
        await redis.expire(count_key, HOUR_SECONDS)
    signals = (("new-device", not await redis.exists(device_key), 1),
               ("unusual-activity", count >= FREQUENT_COUNT, 1),
               ("recent-security-event", bool(await redis.exists(f"risk:security-event:{subject}")), 1))
    score = sum(weight for _, present, weight in signals if present)
    return [code for code, present, _ in signals if present] if score >= STEP_UP_SCORE else []


async def remember_device(request, subject: str) -> None:
    await request.app.state.redis.setex(f"risk:device:{subject}:{fingerprint(request)}", DEVICE_SECONDS, "1")
