"""Exempt PF validation, Form 13 legs and signed trust passbook cache."""
import asyncio

from sqlalchemy import text

from tests.test_ecr_api import SEED, _deliver, ctx, ecr_line, hdr  # noqa: F401


def transition(case, uan, frm, to):
    return {"process": "transfer_form13", "instance_id": case, "subject_ref": uan,
            "to_state": "APPROVED", "data": {"from_account_link_id": frm, "to_account_link_id": to}}


def test_exempt_ecr_rejects_pf_shares():
    from app.domain.ecr import validate
    from epfo_persistence.policy import baseline
    member = next(m for m in SEED["members"] if m["uan"] == "100000000911")
    report = validate(ecr_line(member["uan"], member["name"]), "ECR_TXT", "2026-08", [member], baseline(),
                      exempt_trust=SEED["exempted_establishment"]["trust_name"])
    issues = [x for x in report["issues"] if x["code"] == "E-EXEMPTED-PF"]
    assert len(issues) == 2 and not report["valid"]


def test_transfer_directions_and_member_office_legs(ctx):
    client, q = ctx
    from app.infra.transfers import on_process_transitioned
    for case, uan, frm, to, direction, state in (
        ("CASE-EPFO", "100000000007", "AL-0008", "AL-0009", "EPFO_TO_EPFO", "COMPLETED"),
        ("CASE-TO-TRUST", "100000000911", "AL-0914", "AL-0915", "EPFO_TO_TRUST", "SENT_TO_TRUST"),
        ("CASE-FROM-TRUST", "100000000912", "AL-0918", "AL-0919", "TRUST_TO_EPFO", "AWAITING_TRUST")):
        payload = transition(case, uan, frm, to)
        _deliver(on_process_transitioned, payload, "ProcessTransitioned.v1")
        _deliver(on_process_transitioned, payload, "ProcessTransitioned.v1")
        assert q(f"SELECT direction,pf_leg,eps_leg FROM transfer_legs WHERE transfer_id='{case}'") == [
            (direction, state, "WAITING_FOR_PF")]
    assert q("SELECT COUNT(*) FROM journals WHERE business_key='TRANSFER-CASE-FROM-TRUST'")[0][0] == 0
    assert q("SELECT COUNT(*) FROM journals WHERE business_key='TRANSFER-CASE-TO-TRUST'")[0][0] == 1
    assert q("SELECT COUNT(*) FROM journal_lines WHERE account_code='PAYABLE_TO_TRUSTS'")[0][0] == 2
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='TrustTransferRequested.v1'")[0][0] == 1
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='TransferPosted.v1'")[0][0] == 2
    member = hdr(SEED["keycloak_subjects"]["member-p"], "member", [], establishment=None)
    own = client.get("/api/v1/members/me/transfer-legs", headers=member).json()["data"]["transfers"]
    assert [x["transfer_id"] for x in own] == ["CASE-TO-TRUST"]
    office = hdr(SEED["keycloak_subjects"]["do-caseworker"], "fo.da_accounts", [], establishment=None)
    shown = client.get("/api/v1/office/transfers/CASE-FROM-TRUST/legs", headers=office).json()["data"]
    assert shown["pf_leg"]["state"] == "AWAITING_TRUST" and "Waiting for the PF" in shown["pf_leg"]["label"]
    assert client.get("/api/v1/office/transfers/CASE-FROM-TRUST/legs", headers=member).status_code == 403


def test_annexure_posted_once_and_eps_event(ctx):
    _, q = ctx
    from app.infra.transfers import on_eps_service_transferred, on_process_transitioned, on_trust_annexure_k
    _deliver(on_process_transitioned, transition("CASE-TRUST", "100000000912", "AL-0918", "AL-0919"), "ProcessTransitioned.v1")
    payload = {"annexure_id": "ANN-1", "transfer_id": "CASE-TRUST", "to_account_link_id": "AL-0919",
               "employee_paise": 120000, "employer_paise": 80000, "service_from": "2020-01-01",
               "service_to": "2026-06-30", "breaks_months": 2}
    _deliver(on_trust_annexure_k, payload, "TrustAnnexureKReconciled.v1")
    _deliver(on_trust_annexure_k, payload, "TrustAnnexureKReconciled.v1")
    assert q("SELECT COUNT(*) FROM journals WHERE business_key='TRUST-ANN-1'")[0][0] == 1
    assert q("SELECT pf_leg FROM transfer_legs WHERE transfer_id='CASE-TRUST'") == [("COMPLETED",)]
    _deliver(on_eps_service_transferred, {"transfer_id": "CASE-TRUST", "from_account_link_id": "AL-0918",
                                         "to_account_link_id": "AL-0919", "service_months": 76, "breaks_months": 2},
             "EpsServiceTransferred.v1")
    assert q("SELECT eps_leg FROM transfer_legs WHERE transfer_id='CASE-TRUST'") == [("COMPLETED",)]
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='TransferPosted.v1'")[0][0] == 1


def test_trust_passbook_fresh_cached_stale_unavailable(ctx, monkeypatch):
    client, _ = ctx
    import app.infra.db as db
    import app.infra.trust_passbook as trust
    calls = []
    async def fetch(trust_id, account):
        calls.append(account)
        return {"employee_paise": 100, "employer_paise": 50, "entries": [], "service_from": "2020-01-01", "service_to": None}
    monkeypatch.setattr(trust, "_fetch_trust", fetch)
    headers = hdr(SEED["keycloak_subjects"]["member-p"], "member", [], establishment=None)
    url = "/api/v1/members/me/accounts/AL-0915/passbook"
    first = client.get(url, headers=headers).json()["data"]["accounts"][0]["trust"]
    second = client.get(url, headers=headers).json()["data"]["accounts"][0]["trust"]
    assert first == second and calls == ["AL-0915"] and first["balance"]["employee_paise"] == 100
    ordinary = client.get("/api/v1/members/me/accounts/AL-0914/passbook", headers=headers).json()["data"]["accounts"][0]
    assert "trust" not in ordinary and calls == ["AL-0915"]
    async def expire():
        async with db.engine().begin() as connection:
            await connection.execute(text("UPDATE trust_passbook_cache SET fetched_at='2000-01-01'"))
    asyncio.run(expire())
    async def fail(*_):
        raise OSError("trust unavailable")
    monkeypatch.setattr(trust, "_fetch_trust", fail)
    stale = client.get(url, headers=headers).json()["data"]["accounts"][0]["trust"]
    assert stale["stale"] and stale["balance"]["employer_paise"] == 50
    async def clear():
        async with db.engine().begin() as connection:
            await connection.execute(text("DELETE FROM trust_passbook_cache"))
    asyncio.run(clear())
    unavailable = client.get(url, headers=headers).json()["data"]["accounts"][0]["trust"]
    assert unavailable["unavailable"] and "Trust" in unavailable["contact"]
