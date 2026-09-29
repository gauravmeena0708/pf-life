"""Idempotently load the synthetic pensioners, member service snapshots and office staff.

Each pensioner's original amount is worked out with the baseline formula; payments are credited up to the
last completed month (mock CPPS)."""
import asyncio
import json
import os
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.domain.pension import catch_up_payments
from app.infra.db import sessions
from app.infra.tables import family_members, member_service, office_staff, pensioners
from epfo_persistence.policy import baseline, pension_on

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")
SYNTHETIC_EPS_WAGES = 1500000          # the synthetic members' EPS wages (₹15,000), for the pension estimate


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    rules = baseline()
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for p in seed.get("pensioners", []):
            if "ppo_id" not in p:
                continue
            result = pension_on(p["pensionable_salary_paise"], p["service_months"], p["age_at_start"], rules)
            values = {k: p[k] for k in ("ppo_id", "subject", "name", "uan", "service_months", "pensionable_salary_paise",
                                        "age_at_start", "office_id", "bank_ifsc", "bank_account_last4")}
            values.update(date_of_birth=date.fromisoformat(p["date_of_birth"]), pension_start=date.fromisoformat(p["pension_start"]),
                          original_monthly_paise=result["monthly_paise"], original_rule_version=rules["rule_version"],
                          original_working=result["working"])
            values.update(life_certificate_valid_till=date.fromisoformat(p["life_certificate_valid_till"]) if p.get("life_certificate_valid_till") else None,
                          life_certificate_source="SEED")
            await session.execute(insert(pensioners).values(**values).on_conflict_do_nothing())
            await session.execute(update(pensioners).where(pensioners.c.ppo_id == p["ppo_id"], pensioners.c.life_certificate_valid_till.is_(None))
                                  .values(life_certificate_valid_till=values["life_certificate_valid_till"], life_certificate_source="SEED"))
            row = (await session.execute(select(pensioners).where(pensioners.c.ppo_id == p["ppo_id"]))).mappings().one()
            await catch_up_payments(session, dict(row))
        for m in seed["members"]:
            for i, n in enumerate(m.get("nominations", []), start=1):      # the family on record (from the nomination)
                if n.get("date_of_birth") and not (await session.execute(select(family_members.c.id).where(
                        family_members.c.id == f"FAM-{m['uan']}-{i}"))).first():
                    await session.execute(insert(family_members).values(
                        id=f"FAM-{m['uan']}-{i}", uan=m["uan"], name=n["name"], relation="SPOUSE" if n["relation"] == "SPOUSE" else "CHILD",
                        date_of_birth=date.fromisoformat(n["date_of_birth"]), subject=n.get("subject")))
            # a member without a login (e.g. deceased) is kept under a placeholder subject
            values = {"subject": m.get("subject") or f"NO-LOGIN-{m['uan']}", "name": m["name"], "date_of_birth": date.fromisoformat(m["date_of_birth"]),
                      "date_of_joining": date.fromisoformat(m["date_of_joining"]),
                      "date_of_exit": date.fromisoformat(m["date_of_exit"]) if m.get("date_of_exit") else None,
                      "eps_wages_paise": SYNTHETIC_EPS_WAGES, "office_id": seed["establishment"]["office_id"], "uan": m["uan"],
                      "account_link_id": m["account_link_id"]}
            if (await session.execute(select(member_service.c.subject).where(member_service.c.subject == values["subject"]))).first():
                await session.execute(update(member_service).where(member_service.c.subject == values["subject"]).values(**values))
            else:
                await session.execute(insert(member_service).values(**values))
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
    print(f"pension-service seeded: {len([p for p in seed.get('pensioners', []) if 'ppo_id' in p])} pensioners")


if __name__ == "__main__":
    asyncio.run(main())
