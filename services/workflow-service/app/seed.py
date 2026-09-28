"""Idempotently load the synthetic office and office postings."""
import asyncio
import json
import os

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from datetime import date

from app.infra.tables import member_accounts, office_staff, offices, subject_offices

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
            values = {"office_id": seed["establishment"]["office_id"], "zone_id": office.get("zone_id"),
                      "member_subject": m.get("subject"), "establishment_id": seed["establishment"]["establishment_id"]}
            statement = insert(subject_offices).values(subject_ref=m["uan"], **values)
            await session.execute(statement.on_conflict_do_update(index_elements=[subject_offices.c.subject_ref], set_=values))
            # Member accounts: the current one and any earlier member IDs. Exits and transfers move them after
            # the first load (events), so a re-seed does not overwrite them.
            for a in [{**m, "establishment_id": seed["establishment"]["establishment_id"]}, *m.get("previous_employments", [])]:
                await session.execute(insert(member_accounts).values(
                    account_link_id=a["account_link_id"], uan=m["uan"], member_subject=m.get("subject"), establishment_id=a["establishment_id"],
                    date_of_joining=date.fromisoformat(a["date_of_joining"]),
                    date_of_exit=date.fromisoformat(a["date_of_exit"]) if a.get("date_of_exit") else None).on_conflict_do_nothing())
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(
                subject=s["subject"], username=s["username"], stakeholder=s["stakeholder"],
                office_id=s["office_id"]).on_conflict_do_nothing())
    print(f"workflow-service seeded: office {office['office_id']}, {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
