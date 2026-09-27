"""Idempotently load complainant routing (member → regional office and zone) and office postings."""
import asyncio
import json
import os

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import complainants, office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    office_id, zone_id = seed["establishment"]["office_id"], seed["office"]["zone_id"]
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for m in seed["members"]:
            if m.get("subject"):
                await session.execute(insert(complainants).values(subject=m["subject"], office_id=office_id,
                                                                  zone_id=zone_id).on_conflict_do_nothing())
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
    print(f"grievance-service seeded: complainants routed to {office_id} / {zone_id}")


if __name__ == "__main__":
    asyncio.run(main())
