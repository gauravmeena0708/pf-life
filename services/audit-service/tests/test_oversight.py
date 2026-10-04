"""Security reporting and concurrent audit use the seeded officers' current postings."""
import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_audit_log import SEED, ctx, hdr  # noqa: F401 (fixture)

S = SEED["keycloak_subjects"]
INCIDENTS = "/api/v1/security/incidents"
ALERTS = "/api/v1/audit/concurrent/alerts"


def outbox(event_type):
    from app.infra.db import engine

    async def read():
        async with engine().connect() as connection:
            return (await connection.execute(text("SELECT payload FROM outbox WHERE event_type=:t ORDER BY id"),
                                             {"t": event_type})).scalars().all()
    return [(json.loads(p) if isinstance(p, str) else p)["envelope"]["payload"] for p in asyncio.run(read())]


def incident(category="MALWARE", severity="HIGH", hours_ago=1):
    return {"title": "Suspicious access detected", "category": category, "severity": severity,
            "detected_at": (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
            "description": "The analyst confirmed suspicious activity in the portal.",
            "affected_systems": ["member-service"], "related_event_ids": []}


def security(body, step=True):
    return hdr("ho.security", S["security-analyst"],
               {"action": "record-security-incident", "resource_id": f"{body['category']}:{body['severity']}"} if step else None)


@pytest.mark.parametrize("category,severity,hours_ago,required,late", [
    ("MALWARE", "HIGH", 1, True, False),
    ("OTHER", "LOW", 1, False, False),
    ("DATA_BREACH", "LOW", 1, True, False),
    ("MALWARE", "HIGH", 8, True, True),
])
def test_cert_in_reporting_window_and_categories(ctx, category, severity, hours_ago, required, late):
    client, *_ = ctx
    body = incident(category, severity, hours_ago)
    response = client.post(INCIDENTS, json=body, headers=security(body))
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    report = data["cert_in"]
    assert report["required"] is required and report["late"] is late
    assert datetime.fromisoformat(report["due_by"]) == datetime.fromisoformat(body["detected_at"]) + timedelta(hours=6)
    if required:
        assert report["acknowledgement"].startswith("CERTIN-MOCK-")
        assert datetime.fromisoformat(report["reported_at"]) >= datetime.fromisoformat(body["detected_at"])
    else:
        assert report["acknowledgement"] is None and report["reported_at"] is None
    assert outbox("SecurityIncidentRecorded.v1") == [{"incident_id": data["incident_id"], "category": category,
                                                    "severity": severity, "cert_in_reportable": required, "cert_in_late": late}]
    for role, subject in (("ho.security", "security-analyst"), ("ho.audit", "auditor")):
        listed = client.get(INCIDENTS, headers=hdr(role, S[subject]))
        assert listed.status_code == 200
        assert [i["incident_id"] for i in listed.json()["data"]] == [data["incident_id"]]


def test_security_incidents_require_bound_step_up_and_reject_future_detection(ctx):
    client, *_ = ctx
    body = incident()
    assert client.post(INCIDENTS, json=body, headers=security(body, step=False)).status_code == 428
    for action, resource in (("record-security-incident", "MALWARE:LOW"), ("other-action", "MALWARE:HIGH")):
        assert client.post(INCIDENTS, json=body, headers=hdr("ho.security", S["security-analyst"],
                           {"action": action, "resource_id": resource})).status_code == 403
    future = incident(hours_ago=-1)
    assert client.post(INCIDENTS, json=future, headers=security(future)).status_code == 422
    member = hdr("member", S["member-a"])
    assert client.post(INCIDENTS, json=body, headers=member).status_code == 403
    assert client.get(INCIDENTS, headers=member).status_code == 403
    assert outbox("SecurityIncidentRecorded.v1") == []


def test_today_extract_flags_decisions_and_movements_but_not_contributions(ctx):
    client, deliver, _ = ctx
    samples = [
        ("ClaimDecisionRecorded.v1", {"claim_id": "CLM-HIGH", "decision": "APPROVED", "amount_paise": 6000000},
         ["HIGH_VALUE_SETTLEMENT"], "CLM-HIGH", 6000000),
        ("LedgerAdjusted.v1", {"adjustment_id": "ADJ-PAST", "appendix_type": "PAST_ACCUMULATION",
                               "postings": [{"side": "credit", "account_link_id": "AL-0001", "amount_paise": 1000}]},
         ["PAST_ACCUMULATION_CREDIT"], "ADJ-PAST", 1000),
        ("TransferPosted.v1", {"transfer_id": "AUTO-TEST", "employee_paise": 4000000, "employer_paise": 2000000},
         ["AUTO_TRANSFER", "HIGH_VALUE_TRANSFER"], "AUTO-TEST", 6000000),
        ("MemberChangeApproved.v1", {"request_id": "JD-NAME", "parameters": [{"parameter": "NAME"}]},
         ["IDENTITY_CHANGED"], "JD-NAME", None),
    ]
    event_ids = []
    for event_type, payload, *_ in samples:
        applied, event = deliver(event_type, office_id="RO-DEMO-01", **payload)
        assert applied is True
        event_ids.append(event["event_id"])
    deliver("ContributionPosted.v1", amount_paise=6000000)
    response = client.get("/api/v1/audit/concurrent/extracts", headers=hdr("ho.audit", S["auditor"]))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["day"] == datetime.now(UTC).date().isoformat() and data["events_scanned"] == 5
    assert [(i["event_type"], i["flags"], i["reference"], i["amount_paise"]) for i in data["items"]] == [
        (event_type, flags, ref, amount) for event_type, _, flags, ref, amount in samples]
    assert [i["event_id"] for i in data["items"]] == event_ids
    assert all(i["office_id"] == "RO-DEMO-01" for i in data["items"])
    assert data["flag_counts"] == {"HIGH_VALUE_SETTLEMENT": 1, "PAST_ACCUMULATION_CREDIT": 1,
                                   "AUTO_TRANSFER": 1, "HIGH_VALUE_TRANSFER": 1, "IDENTITY_CHANGED": 1}


def test_a_fixed_share_of_automatic_settlements_is_sampled_for_post_audit(ctx):
    """P2.21b: one automatically settled claim in AUTO_SAMPLE_ONE_IN is flagged, chosen by the claim number alone — the
    same claims on every download, and an officer-approved claim is never part of the sample."""
    from app.api.oversight_routes import AUTO_SAMPLE_ONE_IN, sampled
    client, deliver, _ = ctx
    ids = [f"CLM-{n:08X}" for n in range(40)]
    picked = [c for c in ids if sampled(c)]
    assert 0 < len(picked) < len(ids) and picked == [c for c in ids if sampled(c)]
    for claim_id in ids:
        deliver("ClaimDecisionRecorded.v1", office_id="RO-DEMO-01", claim_id=claim_id, decision="AUTO_APPROVED", amount_paise=1000000)
    deliver("ClaimDecisionRecorded.v1", office_id="RO-DEMO-01", claim_id=picked[0] + "-OFFICER", decision="APPROVED", amount_paise=1000000)
    data = client.get("/api/v1/audit/concurrent/extracts", headers=hdr("zo.rpfc1_audit", S["zo-audit"])).json()["data"]
    assert data["auto_settlements"] == {"settled": 40, "sampled": len(picked), "one_in": AUTO_SAMPLE_ONE_IN}
    assert [i["reference"] for i in data["items"] if "AUTO_SETTLEMENT_SAMPLE" in i["flags"]] == picked
    assert all(i["office_id"] == "RO-DEMO-01" for i in data["items"])


def test_alert_reply_tracks_office_jurisdiction_after_reposting(ctx):
    client, deliver, _ = ctx
    auditor = hdr("zo.rpfc1_audit", S["zo-audit"])
    oic = hdr("fo.oic", S["ro-oic"])
    body = {"office_id": "RO-DEMO-01", "reference": "CLM-HIGH", "flags": ["HIGH_VALUE_SETTLEMENT"],
            "finding": "Please explain the high-value settlement."}
    before = datetime.now(UTC)
    response = client.post(ALERTS, json=body, headers=auditor)
    after = datetime.now(UTC)
    assert response.status_code == 201, response.text
    alert = response.json()["data"]
    due = datetime.fromisoformat(alert["due_by"]).replace(tzinfo=UTC)
    assert before + timedelta(days=3) <= due <= after + timedelta(days=3)
    assert alert["state"] == "OPEN" and alert["zone_id"] == "ZO-DEMO-01"
    assert outbox("ConcurrentAuditAlertRaised.v1") == [{"alert_id": alert["alert_id"], "office_id": "RO-DEMO-01",
                                                      "reference": body["reference"], "flags": body["flags"]}]
    assert client.post(ALERTS, json={**body, "office_id": "RO-OTHER-01"}, headers=auditor).status_code == 404
    assert [a["alert_id"] for a in client.get(ALERTS, headers=oic).json()["data"]] == [alert["alert_id"]]
    reply = {"reply": "The settlement was checked against the documents.", "action_taken": "Documents reviewed"}
    url = f"{ALERTS}/{alert['alert_id']}/replies"
    response = client.post(url, json=reply, headers=oic)
    assert response.status_code == 200 and response.json()["data"]["state"] == "REPLIED"
    assert response.json()["data"]["reply"]["by"] == S["ro-oic"]
    assert client.post(url, json=reply, headers=oic).status_code == 409
    assert client.get(ALERTS, headers=auditor).json()["data"][0]["state"] == "REPLIED"
    new = client.post(ALERTS, json={**body, "reference": "CLM-NEW"}, headers=auditor).json()["data"]
    assert deliver("StaffPostingChanged.v1", subject=S["ro-oic"], username="ro-oic", stakeholder="fo.oic",
                   office_id="RO-DEMO-02", previous_stakeholder="fo.oic", previous_office_id="RO-DEMO-01")[0] is True
    assert client.post(f"{ALERTS}/{new['alert_id']}/replies", json=reply, headers=oic).status_code == 404
    assert client.get(ALERTS, headers=oic).json()["data"] == []
