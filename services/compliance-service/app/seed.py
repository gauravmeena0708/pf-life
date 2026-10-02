"""Idempotently load office postings and establishment names (scripts/seed/synthetic.json)."""
import asyncio
import json
import os

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import compliance_cases, compliance_officers, demands, establishments, inquiries, inquiry_actions, office_staff

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
        # P2.11d: earlier 7A orders whose dues are still unpaid (synthetic history), with their demand as contribution-service holds it
        from datetime import datetime
        for h in seed.get("compliance_history", {}).get("inquiries", []):
            officer = staff[h["officer"]]["subject"]
            ordered, registered = datetime.fromisoformat(h["ordered_at"]), datetime.fromisoformat(h["registered_at"])
            total = sum(v for d in h["dues"] for k, v in d.items() if k.endswith("_paise"))
            await session.execute(insert(inquiries).values(case_id=h["case_id"], diary_no=h["diary_no"], office_id=staff[h["officer"]]["office_id"],
                establishment_id=h["establishment_id"], dispute="DUES", period_from=h["period_from"], period_to=h["period_to"], inspection_id=None,
                contributory_uans=h["contributory_uans"], officer_rank=h["rank"], officer_subject=officer, registered_at=registered,
                registration_due_at=None, concluded_on=ordered, order_due_at=ordered, state="ORDERED", section="7A", ordered_at=ordered,
                ex_parte=False, order_demand_ids=[h["demand_id"]]).on_conflict_do_nothing())
            await session.execute(insert(compliance_cases).values(case_id=h["case_id"], establishment_id=h["establishment_id"],
                office_id=staff[h["officer"]]["office_id"], kind="INQUIRY_7A", wage_months=[], amount_paise=total, state="CLOSED",
                history=[{"at": h["ordered_at"], "by_role": "seed", "action": "ORDERED", "note": h["reasoning"]}], opened_by="seed",
                created_at=registered).on_conflict_do_nothing())
            await session.execute(insert(inquiry_actions).values(action_id=f"SEED-ORDER-{h['case_id']}", case_id=h["case_id"], kind="ORDER",
                actor_subject=officer, occurred_at=ordered, detail={"kind": "7A", "diary_no": h["diary_no"], "dues": h["dues"], "total_paise": total,
                "reasoning": h["reasoning"], "ex_parte": False, "late": False, "text": f"ORDER UNDER SECTION 7A — {h['diary_no']} (synthetic history)",
                "demand_id": h["demand_id"]}).on_conflict_do_nothing())
            await session.execute(insert(demands).values(demand_id=h["demand_id"], establishment_id=h["establishment_id"], kind="DUES_7A",
                trrn="-", wage_month="-", amount_paise=total, days_late=0, state="OPEN", working=json.dumps(h["dues"])).on_conflict_do_nothing())
    print(f"compliance-service seeded: {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
