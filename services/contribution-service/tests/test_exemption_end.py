"""An ended exemption remains effective for earlier wage months and member spells."""
import asyncio
from datetime import date, timedelta

from sqlalchemy import text

from tests.test_ecr_api import SEED, _deliver, ctx, ecr_line, hdr  # noqa: F401
from tests.test_exempted_returns import payload
from tests.test_trust_and_interest import office


EST = "EST-DEMO-0005"
TRUST = SEED["more_exempted_establishments"]["establishments"][0]


def change(status="UNEXEMPTED_COMPLIANCE", ended="2026-09-01", due=None):
    from app.infra.messaging import on_exemption_status_changed
    data = {"establishment_id": EST, "status": status, "ended_on": ended,
            "past_accumulations_due": due or (date.today() - timedelta(days=3)).isoformat()}
    _deliver(on_exemption_status_changed, data, "ExemptionStatusChanged.v1")


def test_event_reseed_and_date_sensitive_surfaces(ctx):
    client, q = ctx
    import app.infra.db as db
    from app.seed import seed
    change()
    change()
    asyncio.run(seed())
    assert q(f"SELECT status,ended_on FROM exempted_establishments WHERE establishment_id='{EST}'")[0][0] == "UNEXEMPTED_COMPLIANCE"
    assert q(f"SELECT exemption_status FROM establishments WHERE id='{EST}'") == [("UNEXEMPTED_COMPLIANCE",)]
    assert q(f"SELECT COUNT(*) FROM exempted_establishments WHERE establishment_id='{EST}'") == [(1,)]

    async def check_dates():
        from app.api.routes import _validation
        neha = next(m for m in SEED["members"] if m["account_link_id"] == "AL-0921")
        content = ecr_line(neha["uan"], neha["name"])
        async with db.sessions()() as session:
            before = await _validation(session, {"id": "test", "establishment_id": EST, "wage_month": "2026-08",
                                                 "version": 1, "content": content, "format": "ECR_TXT"})
            after = await _validation(session, {"id": "test", "establishment_id": EST, "wage_month": "2026-09",
                                                "version": 1, "content": content, "format": "ECR_TXT"})
            return before, after
    before, after = asyncio.run(check_dates())
    assert any(x["code"] == "E-EXEMPTED-PF" for x in before["issues"])
    assert not any(x["code"] == "E-EXEMPTED-PF" for x in after["issues"])

    trust_user = TRUST["trust_users"][0]["subject"]
    earlier = client.post("/api/v1/exempted/me/returns", json=payload(month="2026-07"),
                          headers=hdr(trust_user, "exempted.trust", [], establishment=None))
    assert earlier.status_code == 201, earlier.text
    response = client.post("/api/v1/exempted/me/returns", json=payload(month="2026-09"),
                           headers=hdr(trust_user, "exempted.trust", [], establishment=None))
    assert response.status_code == 409 and "returns stop (link removed)" in response.text
    ranking = client.get("/api/v1/office/exempted/rankings?month=2026-09",
                         headers=office(SEED["keycloak_subjects"]["ro-exemption"], "fo.exemption"))
    assert EST not in {r["establishment_id"] for r in ranking.json()["data"]["rankings"]}

    async def assign_subject():
        async with db.engine().begin() as connection:
            await connection.execute(text("UPDATE establishment_members SET member_subject='neha-test' WHERE account_link_id='AL-0921'"))
    asyncio.run(assign_subject())
    member = client.get("/api/v1/members/me/accounts/AL-0921/passbook",
                        headers=hdr("neha-test", "member", [], establishment=None))
    assert member.status_code == 200, member.text
    assert "Your PF is with EPFO from 2026-09-01" in member.text


def test_late_ingestion_after_unexempted_compliance(ctx):
    client, q = ctx
    change()
    content = "uan,account_link_id,employee_rupees,employer_rupees,pension_rupees\n100000000913,AL-0921,100,50,0\n"
    step = {"action": "ingest-past-accumulation", "resource_id": EST, "amount_paise": 15000}
    response = client.post(f"/api/v1/office/exempted/{EST}/past-accumulation-ingestions",
                           json={"transfer_reference": "TEXTILE-1", "content": content},
                           headers=office(SEED["keycloak_subjects"]["ro-exemption"], "fo.exemption", step))
    assert response.status_code == 201, response.text
    assert response.json()["data"]["late_days"] == 3
    assert "damages (s.14B) and interest (s.7Q) apply" in response.json()["data"]["note"]
    assert "late_days=3" in q("SELECT detail FROM audit_local WHERE action='exempted.past_accumulation_ingestion'")[0][0]
    import app.infra.db as db
    async def assign_subject():
        async with db.engine().begin() as connection:
            await connection.execute(text("UPDATE establishment_members SET member_subject='neha-test' WHERE account_link_id='AL-0921'"))
    asyncio.run(assign_subject())
    shown = client.get("/api/v1/members/me/accounts/AL-0921/passbook",
                       headers=hdr("neha-test", "member", [], establishment=None))
    assert shown.status_code == 200 and "past accumulations from" not in shown.text
