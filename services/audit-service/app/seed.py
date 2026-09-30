"""Idempotently load office postings (scripts/seed/synthetic.json): who replies to a concurrent-audit alert."""
import asyncio
import json
import os

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.oversight_tables import office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    seed = json.load(open(SEED_FILE, encoding="utf-8"))
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
    print(f"audit-service seeded: {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
