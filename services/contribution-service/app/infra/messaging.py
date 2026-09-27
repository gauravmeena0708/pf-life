"""Event consumers for payment confirmation/return and employer verification projections."""
import json
import uuid
from datetime import UTC, datetime
from sqlalchemy import text
from app.domain.ecr import FIELDS, parse, split
from epfo_persistence.policy import rules_by_version
from epfo_persistence import add_event


async def handle_employer_verified(session, event):
    p=event["payload"]
    await session.execute(text("UPDATE establishments SET status='VERIFIED',verification_ref=:r WHERE id=:id"), {"r":p["verification_ref"],"id":p["establishment_id"]})


async def handle_payment_confirmed(session, event):
    p=event["payload"]
    if p.get("purpose") != "CHALLAN": return
    row=(await session.execute(text("SELECT * FROM challans WHERE trrn=:t FOR UPDATE"), {"t":p["reference_id"]})).mappings().first()
    if not row or row["status"] == "PAID": return
    if int(p["amount_paise"]) != int(row["total_paise"]):
        raise ValueError("confirmed payment amount does not match challan total")
    f=(await session.execute(text("SELECT * FROM ecr_filings WHERE id=:id FOR UPDATE"), {"id":row["filing_id"]})).mappings().first()
    await session.execute(text("UPDATE challans SET status='PAID',payment_id=:p,paid_at=now() WHERE trrn=:t"), {"p":p["payment_id"],"t":row["trrn"]})
    await session.execute(text("UPDATE ecr_filings SET state='PAYMENT_CONFIRMED' WHERE id=:id"), {"id":f["id"]})
    exists=(await session.execute(text("SELECT id FROM journals WHERE business_key=:k"), {"k":p["payment_id"]})).scalar_one_or_none()
    if exists: return
    content,_,_=parse(f["content"],f["format"])
    members=(await session.execute(text("SELECT * FROM establishment_members WHERE establishment_id=:e"), {"e":f["establishment_id"]})).mappings().all()
    rules=await rules_by_version(session, f["rule_version"])   # the exact rules the return was validated and submitted under
    by_uan={m["uan"]:m for m in members}; postings=[]
    # Assemble member specific liabilities and establishment level charges from validated file rows.
    for line in content:
        m=by_uan.get(line["UAN"])
        if not m: continue
        rupees=[int(line[k]) if line.get(k,"0").isdigit() else 0 for k in FIELDS[2:9]]
        gross,epf,eps,edli,ee,eps_share,er=rupees
        for amt,share in ((ee,"employee"),(er,"employer")):
            if amt: postings.append({"account_code":"AC01_EPF","side":"credit","amount_paise":amt*100,"account_link_id":m["account_link_id"],"share":share})
        dob=m["date_of_birth"]
        import calendar
        last_day=calendar.monthrange(int(f["wage_month"][:4]),int(f["wage_month"][5:7]))[1]
        age=int(f["wage_month"][:4])-dob.year-((int(f["wage_month"][5:7]),last_day)<(dob.month,dob.day))
        calculated=split(epf*100,eps*100,age,rules,edli*100)
        for code,amt in (("AC10_EPS",eps_share*100),("AC21_EDLI",calculated["AC21_EDLI"])):
            if amt: postings.append({"account_code":code,"side":"credit","amount_paise":amt})
    report=f["validation_report"] if isinstance(f["validation_report"],dict) else json.loads(f["validation_report"])
    totals=report["summary"]["totals_paise"]
    # Administrative and EDLI levies are charged once at establishment level.
    for code in ("AC02_ADMIN","AC22_EDLI_ADMIN"):
        amt=totals[code]
        if amt: postings.append({"account_code":code,"side":"credit","amount_paise":amt})
    postings.insert(0,{"account_code":"BANK_COLLECTION","side":"debit","amount_paise":p["amount_paise"]})
    if sum(x["amount_paise"] for x in postings if x["side"]=="credit") != p["amount_paise"]:
        raise ValueError("payment amount or ECR share totals do not balance")
    jid=str(uuid.uuid4())
    await session.execute(text("INSERT INTO journals (id,business_key,kind,occurred_at,filing_id) VALUES (:id,:k,'CONTRIBUTION',:at,:f)"), {"id":jid,"k":p["payment_id"],"at":datetime.now(UTC),"f":f["id"]})
    for line in postings:
        await session.execute(text("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise,account_link_id,share) VALUES (:j,:a,:s,:n,:l,:h)"), {"j":jid,"a":line["account_code"],"s":line["side"],"n":line["amount_paise"],"l":line.get("account_link_id"),"h":line.get("share")})
    await session.execute(text("UPDATE ecr_filings SET state='POSTED' WHERE id=:f"), {"f":f["id"]})
    await add_event(session,producer="contribution-service",event_type="ContributionPosted.v1",aggregate_type="ledger_journal",aggregate_id=jid,
       payload={"journal_id":jid,"payment_id":p["payment_id"],"filing_id":f["id"],"establishment_id":f["establishment_id"],"wage_month":f["wage_month"],"postings":postings},correlation_id=event["correlation_id"])


async def handle_payment_returned(session,event):
    p=event["payload"]
    if p.get("reference") is None or p.get("purpose", "CHALLAN") != "CHALLAN": return
    await session.execute(text("UPDATE challans SET status='FAILED' WHERE trrn=:t"), {"t":p["reference"]})
    await session.execute(text("UPDATE ecr_filings SET state='PAYMENT_FAILED' WHERE trrn=:t"), {"t":p["reference"]})
