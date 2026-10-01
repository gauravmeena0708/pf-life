"""Idempotently load synthetic office postings (scripts/seed/synthetic.json)."""
import asyncio
import json
import os
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import fund_positions, office_staff
from app.api.investment_routes import store_positions

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as seed_file:
        seed = json.load(seed_file)
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
        positions = seed.get("fund_positions") or {}
        if positions:
            as_of = date.fromisoformat(positions["as_of"])
            for position in positions.get("positions", []):
                # Seed is repeatable: preserve any later feed replacement for the same snapshot.
                existing = (await session.execute(select(fund_positions.c.id).where(
                    fund_positions.c.fund_manager == position["fund_manager"],
                    fund_positions.c.fund == position["fund"],
                    fund_positions.c.as_of == as_of))).scalar_one_or_none()
                if existing is None:
                    await store_positions(session, position["fund_manager"], position["fund"], as_of,
                                          position["holdings"])
    print(f"reporting-service seeded: {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
