"""Internal audit and member privacy workflows use postings, rules and bound step-up."""
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.infra.oversight_tables import internal_paras
from tests.test_audit_log import SEED, ctx, hdr  # noqa: F401
from tests.test_oversight import outbox

S = SEED["keycloak_subjects"]
REPORTS = "/api/v1/audit/internal/reports"
PARAS = "/api/v1/audit/internal/paras"
MINE = "/api/v1/members/me/privacy-requests"
QUEUE = "/api/v1/privacy/requests"


def report(client, office_id="RO-DEMO-01"):
    return client.post(REPORTS, json={"office_id": office_id, "period_from": "2026-01-01", "period_to": "2026-03-31",
                                      "scope": "Review of claim settlement and account controls."},
                       headers=hdr("zo.internal_audit", S["zo-internal-audit"]))


def para(client, report_id):
    return client.post(f"{REPORTS}/{report_id}/paras", json={"category": "CLAIMS",
                       "observation": "Settlement records require a documented explanation.",
                       "amount_at_risk_paise": 1200, "references": ["CLM-1"],
                       "recommendation": "Review the source documents."},
                       headers=hdr("zo.internal_audit", S["zo-internal-audit"]))


def test_internal_audit_jurisdiction_replies_and_decisions(ctx):
    client, deliver, _ = ctx
    oic = hdr("fo.oic", S["ro-oic"])
    auditor = hdr("zo.internal_audit", S["zo-internal-audit"])
    ho = hdr("ho.audit", S["auditor"])
    assert report(client, "RO-OTHER-01").status_code == 404
    assert client.post(REPORTS, json={"office_id": "RO-DEMO-01", "period_from": "2026-03-31",
                                      "period_to": "2026-01-01", "scope": "Review of claim settlement and account controls."},
                       headers=auditor).status_code == 400
    assert report(client, "RO-DEMO-02").status_code == 201
    second = report(client).json()["data"]
    assert second["paras"] == [] and second["period"] == {"from": "2026-01-01", "to": "2026-03-31"}
    raised = para(client, second["report_id"])
    assert raised.status_code == 201, raised.text
    item = raised.json()["data"]
    pid = item["para_id"]
    assert item["reply_due"] == (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    assert outbox("AuditParaRaised.v1") == [{"para_id": pid, "report_id": second["report_id"],
                                           "office_id": "RO-DEMO-01", "category": "CLAIMS",
                                           "reply_due": item["reply_due"]}]
    assert [p["para_id"] for p in client.get(PARAS, headers=oic).json()["data"]] == [pid]
    assert [p["para_id"] for p in client.get(PARAS, headers=auditor).json()["data"]] == [pid]
    assert [p["para_id"] for p in client.get(PARAS, headers=ho).json()["data"]] == [pid]
    assert client.get(PARAS, headers=hdr("member", S["member-a"])).status_code == 403
    assert client.post(f"{REPORTS}/{second['report_id']}/paras", json={"category": "INVALID"},
                       headers=auditor).status_code == 400

    from app.infra.db import sessions
    async def make_late():
        async with sessions()() as session, session.begin():
            await session.execute(update(internal_paras).where(internal_paras.c.para_id == pid)
                                  .values(reply_due=datetime.now(UTC).date() - timedelta(days=1)))
    asyncio.run(make_late())
    assert client.get(PARAS, params={"state": "OPEN"}, headers=oic).json()["data"][0]["overdue"] is True
    reply_url = f"{PARAS}/{pid}/replies"
    body = {"reply": "We checked the settlement against source files.", "action_taken": "Files reviewed", "request_drop": False}
    assert client.post(reply_url, json=body, headers=hdr("fo.oic", "another-oic")).status_code == 403
    replied = client.post(reply_url, json=body, headers=oic)
    assert replied.status_code == 200, replied.text
    assert replied.json()["data"]["replies"][0]["late"] is True
    assert client.post(reply_url, json=body, headers=oic).status_code == 409
    decision_url = f"{PARAS}/{pid}/decisions"
    assert client.post(decision_url, json={"decision": "KEEP", "note": "Further work required"}, headers=ho).status_code == 428
    keep = client.post(decision_url, json={"decision": "KEEP", "note": "Further work required"},
                       headers=hdr("ho.audit", S["auditor"], {"action": "decide-audit-para", "resource_id": pid}))
    assert keep.status_code == 200, keep.text
    assert keep.json()["data"]["state"] == "OPEN"
    assert client.post(reply_url, json=body, headers=oic).status_code == 200
    drop = client.post(decision_url, json={"decision": "DROP", "note": "Resolved with evidence"},
                       headers=hdr("ho.audit", S["auditor"], {"action": "decide-audit-para", "resource_id": pid}))
    assert drop.status_code == 200 and drop.json()["data"]["state"] == "DROPPED"
    assert client.post(reply_url, json=body, headers=oic).status_code == 409
    assert [x["decision"] for x in outbox("AuditParaDecided.v1")] == ["KEPT", "DROPPED"]

    new = para(client, second["report_id"]).json()["data"]
    deliver("StaffPostingChanged.v1", subject=S["ro-oic"], username="ro-oic", stakeholder="fo.oic",
            office_id="RO-DEMO-02", previous_stakeholder="fo.oic", previous_office_id="RO-DEMO-01")
    assert client.post(f"{PARAS}/{new['para_id']}/replies", json=body, headers=oic).status_code == 404
    assert client.get(PARAS, headers=oic).json()["data"] == []


def test_privacy_owner_queue_decision_and_role_boundaries(ctx):
    client, *_ = ctx
    a = hdr("member", S["member-a"])
    b = hdr("member", S["member-b"])
    dpo = hdr("ho.data_protection", S["ho-dpo"])
    created = client.post(MINE, json={"kind": "ERASURE", "details": "Please erase obsolete profile data."}, headers=a)
    assert created.status_code == 201, created.text
    request = created.json()["data"]
    rid = request["request_id"]
    assert request["due_on"] == (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    assert client.get(MINE, headers=b).json()["data"] == []
    assert client.get(MINE, headers=a).json()["data"][0]["request_id"] == rid
    assert client.get(QUEUE, headers=a).status_code == 403
    assert client.post(f"{QUEUE}/{rid}/decisions", json={"decision": "FULFILLED",
                       "answer": "We supplied the account records requested."}, headers=a).status_code == 403
    assert client.post(MINE, json={"kind": "ACCESS", "details": "My account records"}, headers=dpo).status_code == 403
    queued = client.get(QUEUE, params={"state": "OPEN"}, headers=dpo).json()["data"]
    assert len(queued) == 1 and queued[0]["member_subject"] == S["member-a"]
    assert queued[0]["member_reference"].startswith("****") and "details" not in queued[0]
    url = f"{QUEUE}/{rid}/decisions"
    body = {"decision": "PARTLY_FULFILLED", "answer": "We removed the obsolete details from your profile."}
    step = hdr("ho.data_protection", S["ho-dpo"], {"action": "decide-privacy-request", "resource_id": rid})
    assert client.post(url, json={**body, "legal_basis": "Records retained under the EPF Scheme"}, headers=dpo).status_code == 428
    assert client.post(url, json=body, headers=step).status_code == 400
    result = client.post(url, json={**body, "legal_basis": "Records retained under the EPF Scheme"}, headers=step)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["state"] == "PARTLY_FULFILLED"
    assert client.post(url, json={**body, "legal_basis": "Records retained under the EPF Scheme"}, headers=step).status_code == 409
    assert client.get(MINE, headers=a).json()["data"][0]["answer"] == body["answer"]
    assert client.get(MINE, headers=b).json()["data"] == []
    assert client.get(QUEUE, params={"state": "OPEN"}, headers=dpo).json()["data"] == []
    assert outbox("PrivacyRequestDecided.v1") == [{"request_id": rid, "kind": "ERASURE", "decision": "PARTLY_FULFILLED"}]
