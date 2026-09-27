REVOCATION_TTL_SECONDS = 9 * 60 * 60


async def is_revoked(redis, subject: str, establishment_id: str | None = None, grant_id: str | None = None) -> bool:
    if await redis.exists(f"revoked:subject:{subject}"):
        return True
    if establishment_id and grant_id:
        return bool(await redis.exists(f"revoked:grant:{subject}:{establishment_id}:{grant_id}"))
    return False


async def record_revocation(redis, value: dict) -> None:
    subject = value.get("subject")
    if not subject:
        raise ValueError("revocation response has no subject")
    if value.get("scope") == "subject":
        key = f"revoked:subject:{subject}"
    elif value.get("scope") == "grant":
        if not value.get("grant_id"):
            raise ValueError("grant revocation response has no grant id")
        if not value.get("establishment_id"):
            raise ValueError("grant revocation response has no establishment id")
        key = f"revoked:grant:{subject}:{value['establishment_id']}:{value['grant_id']}"
    else:
        raise ValueError("revocation response has no recognized scope")
    await redis.set(key, "1", ex=REVOCATION_TTL_SECONDS)
