"""Idempotently load the synthetic office and office postings."""
import asyncio
import json
import os

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import office_staff, offices, subject_offices

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    office = seed["office"]
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        await session.execute(insert(offices).values(office_id=office["office_id"], name=office["name"],
                                                     zone_id=office.get("zone_id")).on_conflict_do_nothing())
        for m in seed["members"]:               # process subjects (UANs) belong to the establishment's office
            await session.execute(insert(subject_offices).values(subject_ref=m["uan"], office_id=seed["establishment"]["office_id"],
                                                                 zone_id=office.get("zone_id")).on_conflict_do_nothing())
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(
                subject=s["subject"], username=s["username"], stakeholder=s["stakeholder"],
                office_id=s["office_id"]).on_conflict_do_nothing())
    print(f"workflow-service seeded: office {office['office_id']}, {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
