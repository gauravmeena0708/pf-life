"""Idempotently load synthetic employer/member projections into this service database."""
import asyncio
import json
import os
import uuid
from datetime import date, datetime
from sqlalchemy import text
from app.infra.db import sessions


async def seed() -> None:
    with open(os.getenv("SEED_FILE", "/srv/seed/synthetic.json"), encoding="utf-8") as f:
        data = json.load(f)
    establishment = data["establishment"]
    async with sessions()() as session, session.begin():
        # status is owned by EmployerVerified.v1 after the first load; a re-seed must not undo a verification
        await session.execute(text("INSERT INTO establishments (id,legal_name,status) VALUES (:id,:name,:status) ON CONFLICT (id) DO UPDATE SET legal_name=excluded.legal_name"), {"id": establishment["establishment_id"], "name": establishment["legal_name"], "status": establishment["status"]})
        for e in data.get("public_establishments", []):   # earlier employers of members (other member IDs)
            await session.execute(text("INSERT INTO establishments (id,legal_name,status,exemption_status) VALUES (:id,:name,'REGISTERED',:ex) "
                                       "ON CONFLICT (id) DO UPDATE SET exemption_status=excluded.exemption_status"),
                                  {"id": e["establishment_id"], "name": e["legal_name"], "ex": e.get("exemption_status")})
        for m in data["members"]:
            for job in [{**m, "establishment_id": establishment["establishment_id"]}, *m.get("previous_employments", [])]:
                exited = date.fromisoformat(job["date_of_exit"]) if job.get("date_of_exit") else None
                # Exits move with MemberExitMarked.v1 after the first load; a re-seed only refreshes identity fields.
                await session.execute(text("""INSERT INTO establishment_members
                  (uan,name,date_of_birth,account_link_id,member_subject,establishment_id,date_of_joining,date_of_exit,status)
                  VALUES (:uan,:name,:dob,:account,:subject,:est,:joined,:exited,:status)
                  ON CONFLICT (account_link_id) DO UPDATE SET uan=excluded.uan,name=excluded.name,date_of_birth=excluded.date_of_birth,
                  member_subject=excluded.member_subject,establishment_id=excluded.establishment_id,date_of_joining=excluded.date_of_joining"""),
                  {"uan":m["uan"],"name":m["name"],"dob":date.fromisoformat(m["date_of_birth"]),"account":job["account_link_id"],"subject":m.get("subject"),
                   "est":job["establishment_id"],"joined":date.fromisoformat(job["date_of_joining"]),"exited":exited,"status":"EXITED" if exited else "ACTIVE"})
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
        # Balances brought forward (synthetic), as balanced journals keyed OPENING-<account>, posted once.
        for account, bal in data.get("opening_balances", {}).items():
            if account.startswith("_"):
                continue
            key = f"OPENING-{account}"
            at = datetime.fromisoformat(bal["as_of"] + "T23:59:59+00:00")
            if (await session.execute(text("SELECT 1 FROM journals WHERE business_key=:k"), {"k": key})).first():
                # Keep the brought-forward date in step with the seed file (it decides which year earns interest on it).
                await session.execute(text("UPDATE journals SET occurred_at=:at WHERE business_key=:k"), {"at": at, "k": key})
                continue
            journal_id = str(uuid.uuid4())
            total = bal["employee_paise"] + bal["employer_paise"]
            await session.execute(text("""INSERT INTO journals (id,business_key,kind,occurred_at,filing_id,claim_id)
              VALUES (:id,:k,'OPENING_BALANCE',:at,NULL,NULL)"""),
              {"id": journal_id, "k": key, "at": at})
            for code, side, amount, link, share in (
                    ("OPENING_BALANCE_BF", "debit", total, None, None),
                    ("AC01_EPF", "credit", bal["employee_paise"], account, "employee"),
                    ("AC01_EPF", "credit", bal["employer_paise"], account, "employer")):
                await session.execute(text("""INSERT INTO journal_lines (journal_id,account_code,side,amount_paise,account_link_id,share)
                  VALUES (:j,:a,:s,:n,:l,:h)"""), {"j": journal_id, "a": code, "s": side, "n": amount, "l": link, "h": share})


if __name__ == "__main__":
    asyncio.run(seed())
