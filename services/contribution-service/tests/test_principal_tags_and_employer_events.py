"""Contractor tagging and employer-owned establishment projection events."""
import asyncio
import json

from sqlalchemy import text

from tests.test_ecr_api import (EST, GOOD, MONTH, SEED, _deliver, approved, ctx, hdr,
                                preparer, signatory, upload)


def submitted(client):
    f, total = approved(client)
    step = {"action": "submit-ecr", "resource_id": f["filing_id"], "resource_version": f["version"],
            "amount_paise": total}
    response = client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions",
                           headers=signatory(step, **{"Idempotency-Key": "tag-submit", "If-Match": str(f["version"])}))
    assert response.status_code == 201, response.json()
    return f


def tag(client, filing_id, uans, principal="EST-PRINCIPAL", headers=None):
    return client.post(f"/api/v1/employers/me/ecr-filings/{filing_id}/principal-employer-tags",
                       json={"principal_establishment_id": principal, "work_order_ref": "WO-123", "uans": uans},
                       headers=headers or preparer())


def test_principal_tag_scopes_validates_and_publishes(ctx):
    client, q = ctx
    f = submitted(client)
    ids = [m["uan"] for m in SEED["members"][:2]]
    fid = f["filing_id"]
    assert tag(client, fid, ids, headers=preparer(establishment="EST-OTHER")).status_code == 404
    assert tag(client, fid, ids, headers=hdr("owner", "employer.owner", ["ecr.prepare"])).status_code == 403
    assert tag(client, fid, ids, headers=hdr("operator", "employer.operator", [])).status_code == 403
    missing = tag(client, fid, [ids[0], "999999999999"])
    assert missing.status_code == 422 and "999999999999" in missing.json()["detail"]
    assert q("SELECT COUNT(*) FROM principal_employer_tags")[0][0] == 0

    response = tag(client, fid, ids)
    assert response.status_code == 201, response.json()
    data = response.json()["data"]
    assert data["members"] == 2 and data["epf_wages_paise"] == 3_000_000
    assert data["contribution_paise"] == 720_000 and data["paid"] is False
    stored = q("SELECT payload FROM outbox WHERE event_type='PrincipalEmployerTagged.v1'")[0][0]
    event = (json.loads(stored) if isinstance(stored, str) else stored)["envelope"]["payload"]
    assert event == data
    assert q("SELECT COUNT(*) FROM audit_local WHERE action='ecr.principal_employer_tagged'")[0][0] == 1
    detail = client.get(f"/api/v1/employers/me/ecr-filings/{fid}", headers=preparer()).json()["data"]
    assert {x["uan"] for x in detail["principal_tags"]} == set(ids)
    assert tag(client, fid, ids).status_code == 201
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='PrincipalEmployerTagged.v1'")[0][0] == 1
    conflict = tag(client, fid, [ids[0]], principal="EST-DIFFERENT")
    assert conflict.status_code == 409
    added = tag(client, fid, [SEED["members"][2]["uan"]]).json()["data"]
    assert added["members"] == 3 and added["contribution_paise"] == 1_080_000
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='PrincipalEmployerTagged.v1'")[0][0] == 2


def test_tag_requires_submitted_filing_and_paid_status_comes_from_challan(ctx):
    client, q = ctx
    uploaded = upload(client).json()["data"]
    f, total = uploaded["filing"], uploaded["validation_report"]["summary"]["totals_paise"]["TOTAL"]
    uan = SEED["members"][0]["uan"]
    assert tag(client, f["filing_id"], [uan]).status_code == 409
    step = {"action": "approve-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    assert client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/approvals", json={"decision": "APPROVE"},
                       headers=signatory(step)).status_code == 200
    step = {"action": "submit-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    assert client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions",
                       headers=signatory(step, **{"Idempotency-Key": "paid-tag", "If-Match": str(f["version"])})).status_code == 201

    import app.infra.db as db
    async def pay():
        async with db.engine().begin() as conn:
            await conn.execute(text("UPDATE challans SET status='PAID' WHERE filing_id=:f"), {"f": f["filing_id"]})
    asyncio.run(pay())
    assert tag(client, f["filing_id"], [uan]).json()["data"]["paid"] is True


def test_closed_establishment_limits_new_wage_months_and_replay_is_safe(ctx):
    client, q = ctx
    from app.main import _employers_router
    payload = {"establishment_id": EST, "closed_on": "2026-08-31", "last_wage_month": MONTH,
               "reason": "illustrative closure"}
    _, event = _deliver(_employers_router, payload, "EstablishmentClosed.v1")
    import app.infra.db as db
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(db.sessions(), event, _employers_router)) is False
    assert str(q(f"SELECT closed_on FROM establishments WHERE id='{EST}'")[0][0]) == "2026-08-31"
    allowed = upload(client)
    assert allowed.status_code == 201, allowed.json()
    later = client.post("/api/v1/employers/me/ecr-filings", json={"wage_month": "2026-09", "format": "ECR_TXT", "content": GOOD},
                        headers=preparer())
    assert later.status_code == 409 and later.json()["type"] == "/problems/establishment-closed"


def test_office_transfer_updates_establishment_copy_idempotently(ctx):
    _, q = ctx
    from app.main import _employers_router
    payload = {"establishment_id": EST, "from_office_id": "RO-DEMO-01", "to_office_id": "RO-NEW-02",
               "effective_from": "2026-09-01"}
    _deliver(_employers_router, payload, "EstablishmentOfficeTransferred.v1")
    _deliver(_employers_router, payload, "EstablishmentOfficeTransferred.v1")
    assert q(f"SELECT office_id FROM establishments WHERE id='{EST}'")[0][0] == "RO-NEW-02"
