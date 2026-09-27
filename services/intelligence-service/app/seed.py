"""Idempotently load office postings (the claim analysis is limited to the officer's own office)."""
import asyncio
import json
import os

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(
                subject=s["subject"], stakeholder=s["stakeholder"], office_id=s["office_id"]).on_conflict_do_nothing())
    print(f"intelligence-service seeded: {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
