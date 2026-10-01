"""Principal employer reads only its contractor's tagged contribution facts."""
import asyncio

import pytest

from tests.test_compliance_reads import employer_headers
from tests.test_read_models import confirmed, ctx, filing

PATH = "/api/v1/employers/me/contractors/EST-CONTRACTOR/compliance"


def tag(deliver, filing_id, month, *, principal="EST-PRINCIPAL", paid=False, work_order="WO-1"):
    return deliver("PrincipalEmployerTagged.v1", {
        "filing_id": filing_id, "wage_month": month,
        "contractor_establishment_id": "EST-CONTRACTOR",
        "principal_establishment_id": principal, "work_order_ref": work_order,
        "members": 3, "epf_wages_paise": 150000, "contribution_paise": 18000,
        "paid": paid,
    })


def test_tagged_months_unpaid_and_principal_scope(ctx):
    client, deliver = ctx
    tag(deliver, "F-AUG", "2026-08", paid=True)
    tag(deliver, "F-SEP", "2026-09")
    tag(deliver, "F-OTHER", "2026-10", principal="EST-OTHER")

    response = client.get(PATH, headers=employer_headers("principal_employer", "EST-PRINCIPAL"))
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "contractor_establishment_id": "EST-CONTRACTOR",
        "principal_establishment_id": "EST-PRINCIPAL",
        "months": [
            {"wage_month": "2026-09", "members": 3, "epf_wages_paise": 150000,
             "contribution_paise": 18000, "paid": False, "filing_id": "F-SEP", "work_order_ref": "WO-1"},
            {"wage_month": "2026-08", "members": 3, "epf_wages_paise": 150000,
             "contribution_paise": 18000, "paid": True, "filing_id": "F-AUG", "work_order_ref": "WO-1"},
        ],
        "unpaid_months": ["2026-09"],
        "note": "Illustrative view of tagged workers and recorded challan payments only.",
    }
    assert client.get(PATH, headers=employer_headers(establishment="EST-OTHER")).json()["data"]["months"][0]["filing_id"] == "F-OTHER"
    assert client.get(PATH, headers=employer_headers(establishment="EST-UNKNOWN")).status_code == 404


def test_other_principals_contractor_is_not_visible(ctx):
    client, deliver = ctx
    tag(deliver, "F-OTHER", "2026-08", principal="EST-OTHER")
    response = client.get(PATH, headers=employer_headers(establishment="EST-PRINCIPAL"))
    assert response.status_code == 404
    assert response.json()["type"] == "/problems/not-found"


def test_challan_payment_marks_tag_paid_and_redelivery_is_idempotent(ctx):
    client, deliver = ctx
    filing(deliver, "F-PAID", "2026-08", "TRRN-PAID", 18000)
    event = tag(deliver, "F-PAID", "2026-08")
    headers = employer_headers(establishment="EST-PRINCIPAL")
    assert client.get(PATH, headers=headers).json()["data"]["unpaid_months"] == ["2026-08"]
    confirmed(deliver, "TRRN-PAID", "CHALLAN")
    assert client.get(PATH, headers=headers).json()["data"]["unpaid_months"] == []

    from app.api.routes import dispatch
    from app.infra.db import sessions
    from epfo_persistence.consumer import apply_once
    assert asyncio.run(apply_once(sessions(), event, dispatch)) is False
    tag(deliver, "F-PAID", "2026-08", paid=False)
    months = client.get(PATH, headers=headers).json()["data"]["months"]
    assert len(months) == 1 and months[0]["paid"] is True


def test_tag_arriving_after_payment_uses_existing_filing_payment(ctx):
    client, deliver = ctx
    filing(deliver, "F-LATE-TAG", "2026-07", "TRRN-LATE-TAG", 18000)
    confirmed(deliver, "TRRN-LATE-TAG", "CHALLAN")
    tag(deliver, "F-LATE-TAG", "2026-07", paid=False)
    assert client.get(PATH, headers=employer_headers(establishment="EST-PRINCIPAL")).json()["data"]["months"][0]["paid"] is True


@pytest.mark.parametrize("stakeholder", ["member", "employer.operator", "contractor"])
def test_other_roles_cannot_read(ctx, stakeholder):
    client, deliver = ctx
    tag(deliver, "F1", "2026-08")
    assert client.get(PATH, headers=employer_headers(stakeholder, "EST-PRINCIPAL")).status_code == 403


def test_missing_establishment_and_unauthenticated(ctx):
    client, _ = ctx
    response = client.get(PATH, headers=employer_headers("principal_employer", None))
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/no-establishment"
    assert client.get(PATH).status_code == 401
