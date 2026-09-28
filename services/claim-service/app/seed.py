"""Idempotently load the synthetic account projection (with opening balances) and office postings."""
import asyncio
import json
import os
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.infra.db import sessions
from app.infra.tables import accounts, office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    office_id = seed["establishment"]["office_id"]
    opening = {k: v for k, v in seed.get("opening_balances", {}).items() if not k.startswith("_")}
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        jobs = [{**m, "establishment_id": seed["establishment"]["establishment_id"]} for m in seed["members"]]
        jobs += [{**m, **job} for m in seed["members"] for job in m.get("previous_employments", [])]   # earlier member IDs
        for m in jobs:
            balance = opening.get(m["account_link_id"], {})
            exists = (await session.execute(select(accounts.c.account_link_id).where(
                accounts.c.account_link_id == m["account_link_id"]))).first()
            if exists:   # balances move with events after the first load; only refresh identity fields
                await session.execute(update(accounts).where(accounts.c.account_link_id == m["account_link_id"])
                                      .values(member_subject=m.get("subject"), office_id=office_id, uan=m["uan"],
                                              pan_verified=m["kyc"]["pan"] == "VERIFIED"))    # exits move with MemberExitMarked.v1
                continue
            await session.execute(insert(accounts).values(
                account_link_id=m["account_link_id"], member_subject=m.get("subject"), uan=m["uan"],
                establishment_id=m["establishment_id"], office_id=office_id,
                date_of_joining=date.fromisoformat(m["date_of_joining"]),
                date_of_exit=date.fromisoformat(m["date_of_exit"]) if m.get("date_of_exit") else None,
                employee_paise=balance.get("employee_paise", 0), employer_paise=balance.get("employer_paise", 0),
                pan_verified=m["kyc"]["pan"] == "VERIFIED"))
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
    print(f"claim-service seeded: {len(seed['members'])} accounts, {len(seed.get('office_staff', []))} office staff")


if __name__ == "__main__":
    asyncio.run(main())
