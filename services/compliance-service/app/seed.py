"""Idempotently load office postings and establishment names (scripts/seed/synthetic.json)."""
import asyncio
import json
import os

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import compliance_officers, establishments, office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    seed = json.load(open(SEED_FILE, encoding="utf-8"))
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for e in [seed["establishment"], *seed.get("public_establishments", [])]:
            await session.execute(insert(establishments).values(establishment_id=e["establishment_id"], legal_name=e["legal_name"],
                                                                office_id=e.get("office_id") or seed["establishment"]["office_id"]).on_conflict_do_nothing())
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
        staff = {s.get("username"): s for s in seed.get("office_staff", [])}
        barred = set(seed.get("compliance_officers", {}).get("barred_from_sensitive_charge", []))
        for officer in seed.get("compliance_officers", {}).get("officers", []):
            posting = staff.get(officer["username"])
            if posting:
                await session.execute(insert(compliance_officers).values(subject=posting["subject"], rank=officer["rank"],
                    office_id=posting["office_id"], barred=officer["username"] in barred or posting["subject"] in barred).on_conflict_do_nothing())
    print(f"compliance-service seeded: {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
