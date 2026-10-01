"""P2.10a: a confirmed CAIU signal becomes a vigilance case; the CVO assigns the inquiry to the zone; zonal vigilance
reports; the CVO decides. Restricted and access-logged; the complainant masked for all but the CVO."""
import asyncio

from sqlalchemy import insert

from tests.test_cases_api import S, ctx, hdr  # noqa: F401 (fixture)
from tests.test_locks_and_freeze import events

CAIU, CVO, ZONE = S["caiu-investigator"], S["vigilance-investigator"], S["zo-vigilance"]
REFERRAL = {"source": "CAIU_SIGNAL", "source_ref": "SIG-0001", "subject_type": "OFFICIAL", "subject_ref": "ro-da-accounts",
            "office_id": "RO-DEMO-01", "allegation": "Claims settled to one bank account for several unrelated members (synthetic).",
            "evidence": [{"kind": "CLAIM", "ref": "CLM-0001"}], "complainant": {"name": "A Colleague", "contact": "desk 4"}}
FINDINGS = {"finding": "PARTLY_SUBSTANTIATED", "report": "The approvals were made without the bank verification the manual requires; "
            "no gain to the official was found (synthetic).", "recommendation": "Minor penalty proceedings and a system check.",
            "evidence_examined": ["CLM-0001", "SIG-0001"]}


def caiu():
    return hdr(CAIU, "ho.caiu")


def cvo(case_id=None):
    return hdr(CVO, "ho.cvo", {"action": "decide-vigilance-case", "resource_id": case_id} if case_id else None)


def zone(case_id=None, subject=ZONE):
    return hdr(subject, "zo.vigilance", {"action": "report-vigilance-findings", "resource_id": case_id} if case_id else None)


def refer(client, deliver, outcome="CONFIRMED", **changes):
    deliver("RiskSignalReviewed.v1", {"signal_id": changes.get("source_ref", "SIG-0001"), "subject_ref": "CLM-0001", "outcome": outcome},
            producer="intelligence-service")
    return client.post("/api/v1/vigilance/referrals", json={**REFERRAL, **changes}, headers=caiu())


def test_only_a_confirmed_signal_is_referred_once(ctx):
    client, q, deliver = ctx
    assert refer(client, deliver, outcome="BENIGN").status_code == 409
    assert client.post("/api/v1/vigilance/referrals", json={**REFERRAL, "source_ref": "SIG-UNSEEN"}, headers=caiu()).status_code == 409
    r = refer(client, deliver)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["vcn"].startswith("VIG/") and r.json()["data"]["state"] == "REFERRED"
    assert refer(client, deliver).json()["type"] == "/problems/already-referred"
    assert client.post("/api/v1/vigilance/referrals", json={**REFERRAL, "source": "RUMOUR"}, headers=caiu()).status_code == 422
    [opened] = events(q, "VigilanceCaseOpened.v1")
    assert "allegation" not in opened and "complainant" not in opened and opened["subject_type"] == "OFFICIAL"


def test_inquiry_findings_and_decision(ctx):
    client, q, deliver = ctx
    case_id = refer(client, deliver).json()["data"]["case_id"]
    assert client.get("/api/v1/vigilance/cases", headers=zone()).json()["data"]["cases"] == []       # not assigned yet
    assert client.get(f"/api/v1/vigilance/cases/{case_id}", headers=zone()).status_code == 404
    url = f"/api/v1/vigilance/cases/{case_id}"
    assert client.post(f"{url}/decisions", json={"decision": "MINOR_PENALTY_PROCEEDINGS", "note": "Too early to decide"}, headers=cvo(case_id)).status_code == 409
    assert client.post(f"{url}/decisions", json={"decision": "ASSIGN_INQUIRY", "note": "Preliminary inquiry by the zone"}, headers=cvo()).status_code == 428
    r = client.post(f"{url}/decisions", json={"decision": "ASSIGN_INQUIRY", "note": "Preliminary inquiry by the zone"}, headers=cvo(case_id))
    assert r.status_code == 200 and r.json()["data"]["state"] == "PI_ASSIGNED" and r.json()["data"]["zone_id"] == "ZO-DEMO-01", r.text
    seen = client.get(url, headers=zone()).json()["data"]
    assert seen["complainant"] == {"masked": True} and seen["evidence"][0] == {"kind": "RISK_SIGNAL", "ref": "SIG-0001"}
    assert client.get(url, headers=cvo()).json()["data"]["complainant"]["name"] == "A Colleague"
    assert client.post(f"{url}/findings", json=FINDINGS, headers=zone()).status_code == 428
    r = client.post(f"{url}/findings", json=FINDINGS, headers=zone(case_id))
    assert r.status_code == 200 and r.json()["data"] == {**r.json()["data"], "state": "PI_REPORTED", "late": False}, r.text
    assert client.post(f"{url}/findings", json=FINDINGS, headers=zone(case_id)).status_code == 409
    r = client.post(f"{url}/decisions", json={"decision": "RETURN_FOR_INQUIRY", "note": "Examine the bank verification logs too"}, headers=cvo(case_id))
    assert r.json()["data"]["state"] == "PI_ASSIGNED"
    client.post(f"{url}/findings", json=FINDINGS, headers=zone(case_id))
    r = client.post(f"{url}/decisions", json={"decision": "MINOR_PENALTY_PROCEEDINGS", "note": "Accepting the zone's recommendation"}, headers=cvo(case_id))
    assert r.json()["data"]["state"] == "ACTION_ORDERED", r.text
    history = [h["action"] for h in client.get(url, headers=cvo()).json()["data"]["history"]]
    assert history == ["REFERRED", "ASSIGN_INQUIRY", "FINDINGS_REPORTED", "RETURN_FOR_INQUIRY", "FINDINGS_REPORTED", "MINOR_PENALTY_PROCEEDINGS"]
    assert [e["finding"] for e in events(q, "VigilanceFindingsRecorded.v1")] == ["PARTLY_SUBSTANTIATED"] * 2
    assert [e["state"] for e in events(q, "VigilanceDecisionRecorded.v1")] == ["PI_ASSIGNED", "PI_ASSIGNED", "ACTION_ORDERED"]
    reads = q(f"SELECT actor_stakeholder FROM audit_local WHERE action='vigilance.case.read' AND target_id='{case_id}'")
    assert {r for (r,) in reads} == {"zo.vigilance", "ho.cvo"}


def test_restricted_to_the_cvo_and_the_assigned_zone(ctx):
    client, q, deliver = ctx
    case_id = refer(client, deliver).json()["data"]["case_id"]
    client.post(f"/api/v1/vigilance/cases/{case_id}/decisions", json={"decision": "ASSIGN_INQUIRY", "note": "Preliminary inquiry by the zone"},
                headers=cvo(case_id))
    for subject, role in ((CAIU, "ho.caiu"), (S["ro-oic"], "fo.oic"), (S["zo-fraud"], "zo.fraud_committee"), (S["member-a"], "member")):
        assert client.get("/api/v1/vigilance/cases", headers=hdr(subject, role)).status_code == 403
        assert client.get(f"/api/v1/vigilance/cases/{case_id}", headers=hdr(subject, role)).status_code == 403
    assert client.post(f"/api/v1/vigilance/cases/{case_id}/decisions", json={"decision": "CLOSED_NO_SUBSTANCE", "note": "Not mine to decide"},
                       headers=zone(case_id)).status_code == 403
    from app.infra.db import sessions
    from app.infra.tables import office_staff

    async def other_zone():
        async with sessions()() as session, session.begin():
            await session.execute(insert(office_staff).values(subject="other-zone-vig", username="zo-vig-2", stakeholder="zo.vigilance", office_id="ZO-DEMO-02"))
    asyncio.run(other_zone())
    assert client.get(f"/api/v1/vigilance/cases/{case_id}", headers=zone(subject="other-zone-vig")).status_code == 404
    assert client.get("/api/v1/vigilance/cases", headers=zone(subject="other-zone-vig")).json()["data"]["cases"] == []
    assert client.post(f"/api/v1/vigilance/cases/{case_id}/findings", json=FINDINGS, headers=zone(case_id, "other-zone-vig")).status_code == 404


def test_a_late_report_is_marked(ctx):
    client, q, deliver = ctx
    case_id = refer(client, deliver).json()["data"]["case_id"]
    client.post(f"/api/v1/vigilance/cases/{case_id}/decisions", json={"decision": "ASSIGN_INQUIRY", "note": "Preliminary inquiry by the zone"},
                headers=cvo(case_id))
    from app.infra.db import sessions
    from app.infra.tables import vigilance_cases
    from sqlalchemy import update
    from datetime import date

    async def overdue():
        async with sessions()() as session, session.begin():
            await session.execute(update(vigilance_cases).values(pi_due=date(2026, 1, 1)))
    asyncio.run(overdue())
    assert client.get("/api/v1/vigilance/cases", headers=zone()).json()["data"]["cases"][0]["overdue"] is True
    r = client.post(f"/api/v1/vigilance/cases/{case_id}/findings", json=FINDINGS, headers=zone(case_id))
    assert r.json()["data"]["late"] is True and events(q, "VigilanceFindingsRecorded.v1")[0]["late"] is True


# ── P2.10b: preventive vigilance ─────────────────────────────────────────────────────────────────
HR = S["hrm-employee"]


def hr(step_for=None):
    return hdr(HR, "ho.hr", {"action": "post-staff", "resource_id": step_for} if step_for else None)


def test_sensitive_posts_and_rotation(ctx):
    client, q, _ = ctx
    data = client.get("/api/v1/vigilance/sensitive-posts", headers=hr()).json()["data"]
    by = {o["username"]: o for o in data["officers"]}
    assert set(by) == {"ro-cashier", "ro-da-compliance"}                          # the seeded officers on sensitive posts
    assert by["ro-cashier"]["posted_since"] == "2023-06-01" and by["ro-cashier"]["rotation"] in ("ROTATION_DUE", "ROTATION_OVERDUE")
    assert data["transfer_list"] and all(by[u]["rotation"] in ("ROTATION_DUE", "ROTATION_OVERDUE") for u in data["transfer_list"])
    assert client.get("/api/v1/vigilance/sensitive-posts", headers=cvo()).status_code == 200
    assert client.get("/api/v1/vigilance/sensitive-posts", headers=hdr(S["ro-oic"], "fo.oic")).status_code == 403


def test_clearance_withheld_while_a_case_names_the_officer(ctx):
    client, q, deliver = ctx
    body = {"username": "do-caseworker", "purpose": "PROMOTION"}
    r = client.post("/api/v1/vigilance/clearances", json=body, headers=hr())
    assert r.status_code == 201 and r.json()["data"]["cleared"] is True, r.text
    case_id = refer(client, deliver, subject_ref="do-caseworker").json()["data"]["case_id"]
    withheld = client.post("/api/v1/vigilance/clearances", json=body, headers=hr()).json()["data"]
    assert withheld["cleared"] is False and "case_ids" not in withheld and "Chief Vigilance Officer" in withheld["reason"]
    assert [c["case_ids"] for c in client.get("/api/v1/vigilance/clearances", headers=cvo()).json()["data"]["clearances"]][0] == [case_id]
    assert "case_ids" not in client.get("/api/v1/vigilance/clearances", headers=hr()).json()["data"]["clearances"][0]
    client.post(f"/api/v1/vigilance/cases/{case_id}/decisions", json={"decision": "CLOSED_NO_SUBSTANCE", "note": "Nothing in the allegation"},
                headers=cvo(case_id))
    assert client.post("/api/v1/vigilance/clearances", json=body, headers=hr()).json()["data"]["cleared"] is True
    assert client.post("/api/v1/vigilance/clearances", json={**body, "purpose": "HOLIDAY"}, headers=hr()).status_code == 422
    assert client.post("/api/v1/vigilance/clearances", json={**body, "username": "nobody-here"}, headers=hr()).status_code == 404
    assert client.post("/api/v1/vigilance/clearances", json=body, headers=cvo()).status_code == 403
    assert [e["cleared"] for e in events(q, "VigilanceClearanceIssued.v1")] == [True, False, True]


def test_posting_to_a_sensitive_post_needs_a_current_clearance(ctx):
    client, q, deliver = ctx
    posting = {"username": "ro-pro", "stakeholder": "fo.cash", "office_id": "RO-DEMO-01", "reason": "Rotation of the cash section (synthetic)"}
    r = client.post("/api/v1/hrm/postings", json=posting, headers=hr("ro-pro"))
    assert r.status_code == 409 and r.json()["type"] == "/problems/vigilance-clearance-needed", r.text
    refer(client, deliver, subject_ref="ro-pro")
    client.post("/api/v1/vigilance/clearances", json={"username": "ro-pro", "purpose": "POSTING_SENSITIVE"}, headers=hr())
    assert client.post("/api/v1/hrm/postings", json=posting, headers=hr("ro-pro")).json()["type"] == "/problems/vigilance-clearance-withheld"
    case_id = q("SELECT case_id FROM vigilance_cases")[0][0]
    client.post(f"/api/v1/vigilance/cases/{case_id}/decisions", json={"decision": "CLOSED_NO_SUBSTANCE", "note": "Nothing in the allegation"},
                headers=cvo(case_id))
    client.post("/api/v1/vigilance/clearances", json={"username": "ro-pro", "purpose": "POSTING_SENSITIVE"}, headers=hr())
    r = client.post("/api/v1/hrm/postings", json=posting, headers=hr("ro-pro"))
    assert r.status_code == 200, r.text
    tenure = {o["username"]: o for o in client.get("/api/v1/vigilance/sensitive-posts", headers=hr()).json()["data"]["officers"]}["ro-pro"]
    assert tenure["tenure_months"] == 0 and tenure["rotation"] == "WITHIN_TENURE"                     # the posting date is today
