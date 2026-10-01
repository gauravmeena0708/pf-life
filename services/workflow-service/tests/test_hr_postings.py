"""HR postings change office jurisdiction; fraud committees see flagged cases in their zone."""
import asyncio

import pytest
from sqlalchemy import insert

from tests.test_cases_api import S, SEED, ctx, hdr, submitted  # noqa: F401 (fixture)
from tests.test_locks_and_freeze import events

PRO = next(row for row in SEED["office_staff"] if row["subject"] == S["ro-pro"])
BODY = {"username": PRO["username"], "stakeholder": "fo.pro", "office_id": "RO-DEMO-02",
        "reason": "Reposted to meet the regional office's staffing needs"}
URL = "/api/v1/hrm/postings"


def test_establishment_office_transfer_moves_subject_jurisdiction_but_keeps_open_case(ctx):
    _, q, deliver = ctx
    submitted(deliver, claim_id="CLM-OFFICE-TRANSFER")
    before = q("SELECT subject_ref FROM subject_offices WHERE establishment_id='EST-DEMO-0001'")
    assert before
    payload = {"establishment_id": "EST-DEMO-0001", "from_office_id": "RO-DEMO-01",
               "to_office_id": "RO-DEMO-02", "effective_from": "2026-10-01"}
    deliver("EstablishmentOfficeTransferred.v1", payload, "employer-service")
    deliver("EstablishmentOfficeTransferred.v1", payload, "employer-service")
    assert q("SELECT subject_ref FROM subject_offices WHERE establishment_id='EST-DEMO-0001' AND office_id='RO-DEMO-02'") == before
    assert q("SELECT office_id, zone_id FROM subject_offices WHERE subject_ref='EST-DEMO-0001'") == [("RO-DEMO-02", "ZO-DEMO-01")]
    assert q("SELECT office_id FROM cases WHERE claim_id='CLM-OFFICE-TRANSFER'") == [("RO-DEMO-01",)]


def hr(step=True, resource=PRO["username"]):
    return hdr(S["hrm-employee"], "ho.hr", {"action": "post-staff", "resource_id": resource} if step else None)


def test_hr_posts_officer_and_emits_previous_posting(ctx):
    client, q, _ = ctx
    assert client.post(URL, json=BODY, headers=hr(step=False)).status_code == 428
    assert client.post(URL, json=BODY, headers=hr(resource="another-officer")).status_code == 403
    assert q("SELECT stakeholder, office_id FROM office_staff WHERE username='ro-pro'") == [(PRO["stakeholder"], PRO["office_id"])]
    assert events(q, "StaffPostingChanged.v1") == []
    response = client.post(URL, json=BODY, headers=hr())
    assert response.status_code == 200, response.text
    assert response.json()["data"]["previous"] == {"stakeholder": PRO["stakeholder"], "office_id": PRO["office_id"]}
    assert q("SELECT stakeholder, office_id FROM office_staff WHERE username='ro-pro'") == [("fo.pro", "RO-DEMO-02")]
    expected = {"subject": PRO["subject"], "username": PRO["username"], "stakeholder": "fo.pro", "office_id": "RO-DEMO-02",
                "previous_stakeholder": PRO["stakeholder"], "previous_office_id": PRO["office_id"]}
    assert events(q, "StaffPostingChanged.v1") == [expected]
    assert client.post(URL, json=BODY, headers=hr()).status_code == 409
    assert events(q, "StaffPostingChanged.v1") == [expected]


@pytest.mark.parametrize("changes,status", [({"username": "missing-officer"}, 404), ({"stakeholder": "member"}, 422)])
def test_hr_rejects_unknown_officer_and_non_office_role(ctx, changes, status):
    client, q, _ = ctx
    assert client.post(URL, json={**BODY, **changes}, headers=hr()).status_code == status
    assert events(q, "StaffPostingChanged.v1") == []


def test_office_administration_cannot_post_an_officer_to_another_office(ctx):
    client, q, _ = ctx
    from app.infra.db import sessions
    from app.infra.tables import office_staff

    # The synthetic HR employee also has a local administration posting for this authorization test.
    admin = S["hrm-employee"]

    async def setup():
        async with sessions()() as session, session.begin():
            await session.execute(insert(office_staff).values(subject=admin, username="test-office-admin",
                                                              stakeholder="fo.admin", office_id="RO-DEMO-01"))
    asyncio.run(setup())
    response = client.post(URL, json=BODY, headers=hdr(admin, "fo.admin", {"action": "post-staff", "resource_id": PRO["username"]}))
    assert response.status_code == 403, response.text
    assert q("SELECT office_id FROM office_staff WHERE username='ro-pro'") == [("RO-DEMO-01",)]
    assert events(q, "StaffPostingChanged.v1") == []


def test_fraud_committee_lists_only_freezes_and_advisory_claims_in_its_zone(ctx):
    client, _, deliver = ctx
    from app.infra.db import sessions
    from app.infra.tables import cases, offices

    submitted(deliver, claim_id="CLM-RISK", signal="SIGNAL-01")
    submitted(deliver, claim_id="CLM-ORDINARY")

    async def setup():
        async with sessions()() as session, session.begin():
            await session.execute(insert(offices).values(office_id="RO-OTHER-01", name="Another zone's office", zone_id="ZO-OTHER-01"))
            for case_id, office, process, signal in (
                ("CASE-FREEZE", "RO-DEMO-01", "member_freeze", None),
                ("CASE-OTHER-ZONE", "RO-OTHER-01", "member_freeze", "SIGNAL-OTHER"),
                ("CASE-ORDINARY-PROCESS", "RO-DEMO-01", "joint_declaration", None),
            ):
                await session.execute(insert(cases).values(
                    case_id=case_id, office_id=office, kind="PROCESS", process=process, subject_ref="100000000002",
                    form_type="", account_link_id="AL-0002", amount_paise=0, rule_version="demo-rules-2026.1",
                    chain=["fo.oic"], state="OPEN", current_role="fo.oic", advisory_signal_id=signal))
    asyncio.run(setup())
    response = client.get("/api/v1/zo/fraud-risk/cases", headers=hdr(S["zo-fraud"], "zo.fraud_committee"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["zone_id"] == "ZO-DEMO-01"
    assert len(data["cases"]) == 2
    freeze = next(c for c in data["cases"] if c["process"] == "member_freeze")
    claim = next(c for c in data["cases"] if c["claim_id"] == "CLM-RISK")
    assert freeze["case_id"] == "CASE-FREEZE" and freeze["why"] == "Account frozen / freeze in progress"
    assert claim["advisory_signal_id"] == "SIGNAL-01" and claim["why"] == "Advisory risk signal on the claim"
    assert all(c["office_id"] == "RO-DEMO-01" for c in data["cases"])
    assert client.get("/api/v1/zo/fraud-risk/cases", headers=hdr(S["member-a"], "member")).status_code == 403
