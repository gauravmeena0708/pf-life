"""The primary member ID of a member (Phase 2, slice 7d): worked out over the member's Aadhaar-verified set — every
UAN with the same verified Aadhaar — whenever a contribution, a new member ID, a transfer or a recredit changes it.
Other services learn it from PrimaryMemberIdChanged.v1."""
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import employments, members
from epfo_persistence import add_event
from epfo_persistence.member_ids import primary_member_id

PRODUCER = "member-service"


async def aadhaar_set(session: AsyncSession, uan: str) -> list[dict[str, Any]]:
    """The member's UANs: the UAN itself and, when its Aadhaar is verified, every UAN with the same verified Aadhaar."""
    m = (await session.execute(select(members).where(members.c.uan == uan))).mappings().first()
    if not m:
        return []
    if not m["aadhaar_ref"] or (m["kyc"] or {}).get("aadhaar") != "VERIFIED":
        return [dict(m)]
    rows = (await session.execute(select(members).where(members.c.aadhaar_ref == m["aadhaar_ref"]))).mappings().all()
    return [dict(r) for r in rows if (r["kyc"] or {}).get("aadhaar") == "VERIFIED"] or [dict(m)]


async def recompute(session: AsyncSession, uan: str, correlation_id: str | None) -> str | None:
    """Work out the primary member ID for the member's set; store it and publish PrimaryMemberIdChanged.v1 if it moved."""
    uans = await aadhaar_set(session, uan)
    ids = [dict(j) for j in (await session.execute(select(employments).where(
        employments.c.member_id.in_([u["member_id"] for u in uans])))).mappings().all()]
    primary = primary_member_id(ids)
    previous = next((u["primary_account_link_id"] for u in uans if u["uan"] == uan), None)
    await session.execute(update(members).where(members.c.member_id.in_([u["member_id"] for u in uans])).values(primary_account_link_id=primary))
    if primary != previous or any(u["primary_account_link_id"] != primary for u in uans):
        owner = next((u for u in uans for j in ids if j["account_link_id"] == primary and j["member_id"] == u["member_id"]), uans[0] if uans else None)
        await add_event(session, producer=PRODUCER, event_type="PrimaryMemberIdChanged.v1", aggregate_type="member", aggregate_id=uan,
                        correlation_id=correlation_id, payload={
                            "uan": owner["uan"] if owner else uan, "set_uans": sorted(u["uan"] for u in uans),
                            "primary_account_link_id": primary or "", "previous_account_link_id": previous or "",
                            "member_ids": sorted(j["account_link_id"] for j in ids)})
    return primary
