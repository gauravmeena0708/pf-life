"""P2.19: cancellation redirects an in-flight trust transfer to EPFO."""
from tests.test_ecr_api import _deliver, ctx  # noqa: F401
from tests.test_exempted_transfers import transition
from tests.test_inoperative import sql


def test_cancelled_trust_redirects_pending_transfer_and_rejects_new_one(ctx):
    client, q = ctx
    from app.infra.messaging import on_exemption_status_changed
    from app.infra.transfers import on_process_transitioned

    _deliver(on_process_transitioned, transition("CANCEL-MID", "100000000911", "AL-0914", "AL-0915"),
             "ProcessTransitioned.v1")
    assert q("SELECT direction,pf_leg FROM transfer_legs WHERE transfer_id='CANCEL-MID'") == [
        ("EPFO_TO_TRUST", "SENT_TO_TRUST")]
    _deliver(on_exemption_status_changed, {"establishment_id": "EST-DEMO-0004", "status": "CANCELLED",
             "ended_on": "2026-09-01", "past_accumulations_due": "2026-10-01"}, "ExemptionStatusChanged.v1")
    assert q("SELECT direction,pf_leg FROM transfer_legs WHERE transfer_id='CANCEL-MID'") == [
        ("EPFO_TO_EPFO", "COMPLETED")]
    assert q("SELECT SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) "
             "FROM journal_lines WHERE account_code='PAYABLE_TO_TRUSTS'")[0][0] == 0
    assert q("SELECT SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END) "
             "FROM journal_lines WHERE account_code='AC01_EPF' AND account_link_id='AL-0915'")[0][0] > 0
    try:
        _deliver(on_process_transitioned, transition("CANCEL-NEW", "100000000911", "AL-0914", "AL-0915"),
                 "ProcessTransitioned.v1")
    except ValueError as exc:
        assert "cancelled" in str(exc).lower()
    else:
        raise AssertionError("new transfer into cancelled trust was accepted")
    assert q("SELECT COUNT(*) FROM transfer_legs WHERE transfer_id='CANCEL-NEW'") == [(0,)]


def test_annexure_from_cancelled_source_trust_still_completes_into_epfo(ctx):
    _, q = ctx
    from app.infra.messaging import on_exemption_status_changed
    from app.infra.transfers import on_process_transitioned, on_trust_annexure_k

    _deliver(on_process_transitioned, transition("SOURCE-MID", "100000000912", "AL-0918", "AL-0919"),
             "ProcessTransitioned.v1")
    _deliver(on_exemption_status_changed, {"establishment_id": "EST-DEMO-0004", "status": "CANCELLED",
             "ended_on": "2026-09-01", "past_accumulations_due": "2026-10-01"}, "ExemptionStatusChanged.v1")
    _deliver(on_trust_annexure_k, {"annexure_id": "SOURCE-ANN", "transfer_id": "SOURCE-MID",
             "to_account_link_id": "AL-0919", "employee_paise": 120000, "employer_paise": 80000,
             "service_from": "2020-01-01", "service_to": "2026-08-31", "breaks_months": 0},
             "TrustAnnexureKReconciled.v1")
    assert q("SELECT direction,pf_leg FROM transfer_legs WHERE transfer_id='SOURCE-MID'") == [
        ("TRUST_TO_EPFO", "COMPLETED")]


def test_new_epfo_spell_at_formerly_exempt_establishment_is_allowed(ctx):
    _, q = ctx
    from app.infra.messaging import on_exemption_status_changed
    from app.infra.transfers import on_process_transitioned

    _deliver(on_exemption_status_changed, {"establishment_id": "EST-DEMO-0004", "status": "CANCELLED",
             "ended_on": "2026-09-01", "past_accumulations_due": "2026-10-01"}, "ExemptionStatusChanged.v1")
    sql("INSERT INTO establishment_members "
        "(uan,name,date_of_birth,account_link_id,member_subject,establishment_id,date_of_joining,status) "
        "SELECT uan,name,date_of_birth,'AL-0915-NEW',member_subject,establishment_id,'2026-10-01','ACTIVE' "
        "FROM establishment_members WHERE account_link_id='AL-0915'")
    _deliver(on_process_transitioned, transition("NEW-EPFO", "100000000911", "AL-0914", "AL-0915-NEW"),
             "ProcessTransitioned.v1")
    assert q("SELECT direction,pf_leg FROM transfer_legs WHERE transfer_id='NEW-EPFO'") == [
        ("EPFO_TO_EPFO", "COMPLETED")]
