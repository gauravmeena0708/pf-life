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
        if data.get('pmvbry_demo'):
            from app.infra.pmvbry import seed_demo
            await seed_demo(session, data['pmvbry_demo'])
        # status is owned by EmployerVerified.v1 after the first load; a re-seed must not undo a verification
        await session.execute(text("INSERT INTO establishments (id,legal_name,status,office_id) VALUES (:id,:name,:status,:office) "
                                   "ON CONFLICT (id) DO UPDATE SET legal_name=excluded.legal_name"),
                              {"id": establishment["establishment_id"], "name": establishment["legal_name"],
                               "status": establishment["status"], "office": establishment.get("office_id")})
        for e in data.get("public_establishments", []):   # earlier employers of members (other member IDs)
            await session.execute(text("INSERT INTO establishments (id,legal_name,status,exemption_status,office_id) VALUES (:id,:name,'REGISTERED',:ex,:office) "
                                       "ON CONFLICT (id) DO UPDATE SET office_id=COALESCE(establishments.office_id,excluded.office_id)"),
                                  {"id": e["establishment_id"], "name": e["legal_name"], "ex": e.get("exemption_status"), "office": e.get("office_id")})
        ex = data.get("exempted_establishment")
        exemptions = ([ex] if ex else []) + data.get("more_exempted_establishments", {}).get("establishments", [])
        for exemption in exemptions:
            await session.execute(text("""INSERT INTO establishments (id,legal_name,status,exemption_status,office_id)
                VALUES (:id,:name,'REGISTERED',:status,:office)
                ON CONFLICT (id) DO NOTHING"""),
                {"id": exemption["establishment_id"], "name": exemption.get("legal_name", exemption["trust_name"]),
                 "status": exemption["status"], "office": exemption.get("office_id", establishment.get("office_id"))})
            await session.execute(text("""INSERT INTO exempted_establishments
                (establishment_id,kind,pf_exempt,pension_exempt,edli_exempt,notification_no,notification_date,
                 effective_from,status,trust_id,trust_name,trust_users)
                VALUES (:id,:kind,:pf,:pension,:edli,:notification,:notified,:effective,:status,:trust,:name,:users)
                ON CONFLICT (establishment_id) DO UPDATE SET trust_name=excluded.trust_name,
                trust_users=excluded.trust_users"""),
                {"id": exemption["establishment_id"], "kind": exemption["kind"], "pf": exemption["pf_exempt"],
                 "pension": exemption["pension_exempt"], "edli": exemption["edli_exempt"], "notification": exemption["notification_no"],
                 "notified": date.fromisoformat(exemption["notification_date"]), "effective": date.fromisoformat(exemption["effective_from"]),
                 "status": exemption["status"], "trust": exemption["trust_id"], "name": exemption["trust_name"],
                 "users": json.dumps(exemption.get("trust_users", []))})
        for m in data["members"]:
            for job in [{"establishment_id": establishment["establishment_id"], **m}, *m.get("previous_employments", [])]:
                exited = date.fromisoformat(job["date_of_exit"]) if job.get("date_of_exit") else None
                # Exits move with MemberExitMarked.v1 after the first load; a re-seed only refreshes identity fields.
                await session.execute(text("""INSERT INTO establishment_members
                  (uan,name,date_of_birth,account_link_id,member_subject,establishment_id,date_of_joining,date_of_exit,status,international_worker)
                  VALUES (:uan,:name,:dob,:account,:subject,:est,:joined,:exited,:status,:iw)
                  ON CONFLICT (account_link_id) DO UPDATE SET uan=excluded.uan,name=excluded.name,date_of_birth=excluded.date_of_birth,
                  member_subject=excluded.member_subject,establishment_id=excluded.establishment_id,date_of_joining=excluded.date_of_joining,
                  international_worker=excluded.international_worker"""),
                  {"uan":m["uan"],"name":m["name"],"dob":date.fromisoformat(m["date_of_birth"]),"account":job["account_link_id"],"subject":m.get("subject"),
                   "est":job["establishment_id"],"joined":date.fromisoformat(job["date_of_joining"]),"exited":exited,"status":"EXITED" if exited else "ACTIVE","iw":bool(m.get("international"))})
        from app.infra.models import OfficeStaff               # P2.9d: postings, for office routes
        for st in data.get("office_staff", []):
            if not (await session.execute(text("SELECT 1 FROM office_staff WHERE subject=:s"), {"s": st["subject"]})).first():
                await session.execute(OfficeStaff.__table__.insert().values(subject=st["subject"], stakeholder=st["stakeholder"],
                                                                            office_id=st["office_id"]))
        trust_returns = data.get("trust_returns")
        if trust_returns and ex and trust_returns["establishment_id"] == ex["establishment_id"]:
            from app.api.exempted_returns_routes import ReturnInput, file_return
            for item in sorted(trust_returns["returns"], key=lambda r: r["wage_month"]):
                if (await session.execute(text("SELECT 1 FROM trust_returns WHERE establishment_id=:e AND wage_month=:m"),
                                          {"e": ex["establishment_id"], "m": item["wage_month"]})).first():
                    continue                                # a re-seed keeps the returns already loaded
                source = dict(item)
                pending = source["claims_opening"] + source["claims_received"] - source["claims_within_days"] - source["claims_beyond_days"]
                if pending and not source.get("pending_reasons"):
                    source["pending_reasons"] = "Not recorded in historical synthetic return"
                await file_return(session, ex["establishment_id"], date.fromisoformat(ex["effective_from"]), ex,
                                  ReturnInput(**source), "seed", "seed", seeded=True)
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
