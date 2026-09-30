"""Idempotently load office postings (the claim analysis is limited to the officer's own office) and, once, the
synthetic circulars."""
import asyncio
import json
import os
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import circulars, office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")
CIRCULARS = [   # synthetic, for the demonstration only
    {"number": "DEMO/CLAIMS/2026/01", "title": "Auto-settlement of advance claims (synthetic)", "category": "CLAIMS",
     "issued_on": date(2026, 4, 1), "summary": "Advance claims within the automatic limit are settled without an officer (illustrative).",
     "body": "SYNTHETIC DEMONSTRATION. Advance claims for medical treatment within the automatic settlement limit in the rule set "
             "are settled without an officer; others follow the approval bands."},
    {"number": "DEMO/PENSION/2026/02", "title": "Digital life certificates (synthetic)", "category": "PENSION",
     "issued_on": date(2026, 5, 15), "summary": "Pensioners may submit a digital life certificate at any time in the year (illustrative).",
     "body": "SYNTHETIC DEMONSTRATION. A digital life certificate is valid for one year from the date it is submitted."},
    {"number": "DEMO/COMPLIANCE/2026/03", "title": "Due date for remittances (synthetic)", "category": "COMPLIANCE",
     "issued_on": date(2026, 6, 1), "summary": "Contributions for a wage month are due by the 15th of the next month (illustrative).",
     "body": "SYNTHETIC DEMONSTRATION. A later payment raises 14B damages and 7Q interest as set in the rule set in force."},
]


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(
                subject=s["subject"], stakeholder=s["stakeholder"], office_id=s["office_id"]).on_conflict_do_nothing())
        if not (await session.execute(select(circulars.c.circular_id).limit(1))).first():   # synthetic circulars, once
            from app.api.circular_routes import CircularInput, publish
            for c in CIRCULARS:
                await publish(session, CircularInput(**c), "SEED")
    print(f"intelligence-service seeded: {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
