"""Events international-service consumes: who works where (member-service)."""
from datetime import date
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import members

BINDINGS = ["member-service.MemberRegistered.v1", "member-service.MemberExitMarked.v1"]


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if event["event_type"] == "MemberRegistered.v1":
        if not (await session.execute(select(members.c.account_link_id).where(members.c.account_link_id == p["account_link_id"]))).first():
            await session.execute(insert(members).values(account_link_id=p["account_link_id"], uan=p["uan"], subject=p.get("member_subject"),
                                                         name=p["name"], establishment_id=p["establishment_id"],
                                                         date_of_joining=date.fromisoformat(p["date_of_joining"])))
    elif event["event_type"] == "MemberExitMarked.v1":
        await session.execute(update(members).where(members.c.account_link_id == p["account_link_id"])
                              .values(date_of_exit=date.fromisoformat(p["date_of_exit"])))
