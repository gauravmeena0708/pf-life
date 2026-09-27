"""Idempotently load synthetic employer/member projections into this service database."""
import asyncio
import json
import os
from datetime import date
from sqlalchemy import text
from app.infra.db import sessions


async def seed() -> None:
    with open(os.getenv("SEED_FILE", "/srv/seed/synthetic.json"), encoding="utf-8") as f:
        data = json.load(f)
    establishment = data["establishment"]
    async with sessions()() as session, session.begin():
        await session.execute(text("INSERT INTO establishments (id,legal_name,status) VALUES (:id,:name,:status) ON CONFLICT (id) DO UPDATE SET legal_name=excluded.legal_name,status=excluded.status"), {"id": establishment["establishment_id"], "name": establishment["legal_name"], "status": establishment["status"]})
        for m in data["members"]:
            await session.execute(text("""INSERT INTO establishment_members
              (uan,name,date_of_birth,account_link_id,member_subject,establishment_id,date_of_joining,date_of_exit,status)
              VALUES (:uan,:name,:dob,:account,:subject,:est,:joined,NULL,'ACTIVE')
              ON CONFLICT (uan) DO UPDATE SET name=excluded.name,date_of_birth=excluded.date_of_birth,
              account_link_id=excluded.account_link_id,member_subject=excluded.member_subject,
              establishment_id=excluded.establishment_id,date_of_joining=excluded.date_of_joining"""),
              {"uan":m["uan"],"name":m["name"],"dob":date.fromisoformat(m["date_of_birth"]),"account":m["account_link_id"],"subject":m.get("subject"),"est":establishment["establishment_id"],"joined":date.fromisoformat(m["date_of_joining"])})
        demo = data["public_lookup_challan"]
        await session.execute(text("""INSERT INTO ecr_filings
          (id,establishment_id,wage_month,filing_type,format,content,version,state,preparer_subject,rule_version,trrn)
          VALUES (:id,:est,:month,'REGULAR','CSV','synthetic public lookup fixture',1,'SUBMITTED','seed','demo-rules-2026.1',:trrn)
          ON CONFLICT (id) DO NOTHING"""), {"id":demo["filing_id"], "est":establishment["establishment_id"],
                                       "month":demo["wage_month"], "trrn":demo["trrn"]})
        await session.execute(text("""INSERT INTO challans
          (trrn,filing_id,establishment_id,status,total_paise,breakdown)
          VALUES (:trrn,:filing,:est,:status,0,'{}') ON CONFLICT (trrn) DO NOTHING"""),
          {"trrn":demo["trrn"],"filing":demo["filing_id"],"est":establishment["establishment_id"],"status":demo["status"]})


if __name__ == "__main__":
    asyncio.run(seed())
