"""Idempotently load postings, establishments, member IDs and the agreement catalogue (scripts/seed/synthetic.json)."""
import asyncio
import json
import os
from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import agreements, establishments, members, office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")
NOTE = "Synthetic catalogue: the partner country is real, the terms shown are illustrative and not the agreement's text."
AGREEMENTS = [  # country, code, in force from, max posting, max extension, totalisation
    ("Belgium", "BEL", "2009-09-01", 60, 0, True), ("Germany", "DEU", "2009-10-01", 48, 12, False),
    ("Switzerland", "CHE", "2011-01-29", 72, 0, True), ("France", "FRA", "2011-07-01", 60, 0, True),
    ("Netherlands", "NLD", "2011-12-01", 60, 0, True), ("Korea", "KOR", "2011-11-01", 60, 36, False),
    ("Japan", "JPN", "2016-10-01", 60, 0, True), ("Australia", "AUS", "2016-01-01", 48, 12, True),
    ("Canada", "CAN", "2015-08-01", 60, 0, True), ("Brazil", "BRA", "2022-07-01", 60, 0, True),
]


async def main() -> None:
    seed = json.load(open(SEED_FILE, encoding="utf-8"))
    est = seed["establishment"]
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for e in [est, *seed.get("public_establishments", [])]:
            await session.execute(insert(establishments).values(establishment_id=e["establishment_id"], legal_name=e["legal_name"],
                                                                office_id=e.get("office_id") or est["office_id"]).on_conflict_do_nothing())
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
        for c, code, since, posting, extension, total in AGREEMENTS:
            await session.execute(insert(agreements).values(country=c, code=code, in_force_from=date.fromisoformat(since),
                                                            max_posting_months=posting, max_extension_months=extension,
                                                            totalisation=total, note=NOTE).on_conflict_do_nothing())
        for m in seed["members"]:
            intl = m.get("international") or {}
            for job in [{**m, "establishment_id": est["establishment_id"]}, *m.get("previous_employments", [])]:
                await session.execute(insert(members).values(
                    account_link_id=job["account_link_id"], uan=m["uan"], subject=m.get("subject"), name=m["name"],
                    establishment_id=job["establishment_id"], date_of_joining=date.fromisoformat(job["date_of_joining"]),
                    date_of_exit=date.fromisoformat(job["date_of_exit"]) if job.get("date_of_exit") else None,
                    international_worker=bool(intl), nationality=intl.get("nationality"),
                    passport_masked=intl.get("passport_masked")).on_conflict_do_nothing())   # exits move with events after the first load
    print(f"international-service seeded: {len(AGREEMENTS)} agreements, {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
