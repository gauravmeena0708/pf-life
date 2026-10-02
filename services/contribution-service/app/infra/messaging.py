"""Event consumers for payment confirmation/return and employer verification projections."""
import json
import uuid
from datetime import UTC, date, datetime
from sqlalchemy import text
from app.domain.ecr import FIELDS, parse, split
from epfo_persistence.policy import rules_by_version
from epfo_persistence import add_event

from app.infra.claims_ledger import on_higher_pension_transfer
from app.infra.transfers import on_trust_annexure_k, on_eps_service_transferred

BINDINGS = ["pension-service.HigherPensionDuesTransferRequested.v1",
            "claim-service.TrustAnnexureKReconciled.v1", "pension-service.EpsServiceTransferred.v1",
            "workflow-service.StaffPostingChanged.v1"]
HANDLERS = {"HigherPensionDuesTransferRequested.v1": on_higher_pension_transfer,
            "TrustAnnexureKReconciled.v1": on_trust_annexure_k,
            "EpsServiceTransferred.v1": on_eps_service_transferred}


async def on_staff_posting(session, event):
    """HR re-posted an officer: office routes follow the new posting (P2.9d)."""
    from app.infra.models import OfficeStaff
    from epfo_persistence.postings import apply_posting
    await apply_posting(session, event, OfficeStaff.__table__)


HANDLERS["StaffPostingChanged.v1"] = on_staff_posting


async def dispatch(session, event):
    handler = HANDLERS.get(event.get("event_type"))
    if handler:
        await handler(session, event)


async def handle_employer_verified(session, event):
    p=event["payload"]
    await session.execute(text("UPDATE establishments SET status='VERIFIED',verification_ref=:r WHERE id=:id"), {"r":p["verification_ref"],"id":p["establishment_id"]})


async def handle_establishment_closed(session, event):
    p = event["payload"]
    await session.execute(text("UPDATE establishments SET closed_on=:closed, last_wage_month=:month WHERE id=:id"),
                          {"closed": date.fromisoformat(p["closed_on"]), "month": p["last_wage_month"],
                           "id": p["establishment_id"]})


async def handle_establishment_office_transferred(session, event):
    p = event["payload"]
    await session.execute(text("UPDATE establishments SET office_id=:office WHERE id=:id"),
                          {"office": p["to_office_id"], "id": p["establishment_id"]})


async def on_exemption_status_changed(session, event):
    p = event["payload"]
    status = p["status"]
    if status not in ("ACTIVE", "UNEXEMPTED_COMPLIANCE", "SURRENDERED", "CANCELLED"):
        raise ValueError(f"Unknown exemption status: {status}")
    ended = date.fromisoformat(p["ended_on"]) if p.get("ended_on") else None
    due = date.fromisoformat(p["past_accumulations_due"]) if p.get("past_accumulations_due") else None
    await session.execute(text("""UPDATE exempted_establishments SET status=:status,ended_on=:ended,
        past_accumulations_due=:due WHERE establishment_id=:id"""),
        {"status": status, "ended": ended, "due": due, "id": p["establishment_id"]})
    await session.execute(text("UPDATE establishments SET exemption_status=:status WHERE id=:id"),
                          {"status": status, "id": p["establishment_id"]})


async def handle_payment_confirmed(session, event):
    p=event["payload"]
    if p.get("purpose") != "CHALLAN": return
    lock=" FOR UPDATE" if session.bind.dialect.name=="postgresql" else ""      # SQLite (unit tests) has no row locks
    row=(await session.execute(text("SELECT * FROM challans WHERE trrn=:t"+lock), {"t":p["reference_id"]})).mappings().first()
    if not row or row["status"] == "PAID": return
    if int(p["amount_paise"]) != int(row["total_paise"]):
        raise ValueError("confirmed payment amount does not match challan total")
    if row.get("kind") == "EEC":                             # past dues under the Employees' Enrolment Campaign, 2026
        from app.api.eec_routes import post_eec_challan
        await post_eec_challan(session, row, p)
        return
    if row.get("kind", "ECR") != "ECR":                      # a direct challan: administrative charges, or 14B / 7Q
        await _post_direct_challan(session, row, p, event)
        return
    f=(await session.execute(text("SELECT * FROM ecr_filings WHERE id=:id"+lock), {"id":row["filing_id"]})).mappings().first()
    await session.execute(text("UPDATE challans SET status='PAID',payment_id=:p,paid_at=:at WHERE trrn=:t"), {"p":p["payment_id"],"t":row["trrn"],"at":datetime.now(UTC)})
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
        dob=m["date_of_birth"] if not isinstance(m["date_of_birth"],str) else datetime.fromisoformat(m["date_of_birth"]).date()
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
    from app.infra.pmvbry import project_paid_filing
    await project_paid_filing(session, f, content, members)
    await _raise_late_payment_demands(session, f, row, rules)
    await add_event(session,producer="contribution-service",event_type="ContributionPosted.v1",aggregate_type="ledger_journal",aggregate_id=jid,
       payload={"journal_id":jid,"payment_id":p["payment_id"],"filing_id":f["id"],"establishment_id":f["establishment_id"],"wage_month":f["wage_month"],"postings":postings},correlation_id=event["correlation_id"])


async def handle_payment_returned(session,event):
    p=event["payload"]
    if p.get("reference") is None or p.get("purpose", "CHALLAN") != "CHALLAN": return
    await session.execute(text("UPDATE challans SET status='FAILED' WHERE trrn=:t"), {"t":p["reference"]})
    await session.execute(text("UPDATE ecr_filings SET state='PAYMENT_FAILED' WHERE trrn=:t"), {"t":p["reference"]})


async def handle_member_change(session, event):
    """A Joint Declaration correction: ECR name and age checks use the corrected record from now on."""
    p = event["payload"]
    for change in p["parameters"]:
        if change["parameter"] == "NAME":
            await session.execute(text("UPDATE establishment_members SET name=:v WHERE uan=:u"), {"v": change["value"], "u": p["uan"]})
        elif change["parameter"] == "DATE_OF_BIRTH":
            await session.execute(text("UPDATE establishment_members SET date_of_birth=:v WHERE uan=:u"),
                                  {"v": datetime.fromisoformat(change["value"]).date(), "u": p["uan"]})


async def handle_inoperative_verified(session, event):
    """Keep the member service's office verification once, including on message redelivery."""
    p = event["payload"]
    await session.execute(text(
        "INSERT INTO inoperative_verifications (account_link_id,uan,co_workers,verified_by_office) "
        "VALUES (:a,:u,:c,:v) ON CONFLICT (account_link_id) DO NOTHING"),
        {"a": p["account_link_id"], "u": p["uan"], "c": int(p["co_workers"]),
         "v": p["verified_by_office"]})


async def _post_direct_challan(session, row, p, event):
    """A paid direct challan: the bank collection against administrative charges or 14B damages / 7Q interest."""
    await session.execute(text("UPDATE challans SET status='PAID',payment_id=:p,paid_at=:at WHERE trrn=:t"),
                          {"p":p["payment_id"],"t":row["trrn"],"at":datetime.now(UTC)})
    if (await session.execute(text("SELECT id FROM journals WHERE business_key=:k"), {"k":p["payment_id"]})).first():
        return
    breakdown=row["breakdown"] if isinstance(row["breakdown"],dict) else json.loads(row["breakdown"])
    lines=[{"account_code":"BANK_COLLECTION","side":"debit","amount_paise":int(p["amount_paise"])}]
    lines+=[{"account_code":code,"side":"credit","amount_paise":amt} for code,amt in breakdown.items() if amt]
    if sum(x["amount_paise"] for x in lines if x["side"]=="credit") != int(p["amount_paise"]):
        raise ValueError("direct challan amount does not balance")
    jid=str(uuid.uuid4())
    await session.execute(text("INSERT INTO journals (id,business_key,kind,occurred_at) VALUES (:id,:k,'DIRECT_CHALLAN',:at)"),
                          {"id":jid,"k":p["payment_id"],"at":datetime.now(UTC)})
    for line in lines:
        await session.execute(text("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise) VALUES (:j,:a,:s,:n)"),
                              {"j":jid,"a":line["account_code"],"s":line["side"],"n":line["amount_paise"]})


async def _raise_late_payment_demands(session, f, challan, rules):
    """Contributions paid after the due date raise 14B damages and 7Q interest demands (illustrative rates)."""
    from epfo_persistence.policy import due_date, late_payment_charges
    paid=datetime.now(UTC).date()
    charges=late_payment_charges(int(challan["total_paise"]), due_date(f["wage_month"], rules), paid, rules)
    if not charges["late"]:
        return
    raised=[]
    for kind,amount in (("DAMAGES_14B",charges["damages_14b_paise"]),("INTEREST_7Q",charges["interest_7q_paise"])):
        key=f"DEM-{challan['trrn']}-{kind[-3:]}"
        raised.append(key)
        if amount and not (await session.execute(text("SELECT 1 FROM demands WHERE demand_id=:d"), {"d":key})).first():
            await session.execute(text("INSERT INTO demands (demand_id,establishment_id,kind,trrn,wage_month,amount_paise,days_late,working,rule_version,state,created_at) "
                                       "VALUES (:d,:e,:k,:t,:m,:a,:days,:w,:r,'OPEN',:at)"),
                                  {"d":key,"e":f["establishment_id"],"k":kind,"t":challan["trrn"],"m":f["wage_month"],"a":amount,
                                   "days":charges["days_late"],"w":charges["working"],"r":rules["rule_version"],"at":datetime.now(UTC)})
    from app.infra.demands import publish
    await publish(session, raised, None)                      # compliance-service and the mock bank see the demands
