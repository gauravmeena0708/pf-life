"""Office postings follow HR (Phase 2, slice 8e): workflow-service owns them and publishes StaffPostingChanged.v1;
each service that scopes officers to an office keeps its own copy (an `office_staff` table with subject,
stakeholder and office_id) and applies the change here, so a re-posted officer sees the new office's work."""
from typing import Any

from sqlalchemy import Table, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession


async def apply_posting(session: AsyncSession, event: dict[str, Any], office_staff: Table) -> None:
    p = event["payload"]
    values = {"stakeholder": p["stakeholder"], "office_id": p["office_id"]}
    if (await session.execute(select(office_staff.c.subject).where(office_staff.c.subject == p["subject"]))).first():
        await session.execute(update(office_staff).where(office_staff.c.subject == p["subject"]).values(**values))
    else:
        await session.execute(insert(office_staff).values(subject=p["subject"], **values))
