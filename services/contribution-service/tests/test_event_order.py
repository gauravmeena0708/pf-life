"""Event ordering and concurrency tests for contribution-service (docs/event-copies.md).

Lead 2: demands table (producers: compliance-service, payment-simulator)
Lead 7: transfer_legs table (producers: claim-service, pension-service)
"""
import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import text

from tests.test_ecr_api import EST, _deliver, ctx, hdr  # noqa: F401


def transition(case: str, uan: str, frm: str, to: str) -> dict[str, Any]:
    return {
        "process": "transfer_form13",
        "instance_id": case,
        "subject_ref": uan,
        "to_state": "APPROVED",
        "data": {"from_account_link_id": frm, "to_account_link_id": to},
    }


# ==============================================================================
# Lead 2: demands table (state, settled_by, realised_paise)
# Producers: compliance-service (DemandRaised.v1, RecoveryRealised.v1)
#            payment-simulator (PaymentConfirmed.v1 [purpose=DEMAND])
# ==============================================================================

def test_lead_2_older_payment_cannot_overwrite_waived_demand(ctx):
    """Lead 2: A demand is waived under VISHWAS by compliance-service (DemandRaised.v1).
    An older/delayed payment confirmation (PaymentConfirmed.v1) arriving later
    must NOT overwrite the waived demand to PAID or post an invalid payment journal.
    """
    _, q = ctx
    from app.infra.demands import on_demand_paid, on_demand_raised

    # 1. Setup: an open demand exists
    _deliver(
        on_demand_raised,
        {"demand_id": "DEM-INIT-1", "establishment_id": EST, "demand_type": "DAMAGES_14B",
         "amount_paise": 150000, "supersedes_demand_ids": [], "working": "14B initial", "rule_version": "r"},
        "DemandRaised.v1",
    )
    assert q("SELECT state, settled_by FROM demands WHERE demand_id='DEM-INIT-1'") == [("OPEN", None)]

    # 2. Compliance waives DEM-INIT-1 under VISHWAS
    _deliver(
        on_demand_raised,
        {"demand_id": "DEM-VISHWAS-1", "establishment_id": EST, "demand_type": "DAMAGES_14B_VISHWAS",
         "amount_paise": 50000, "supersedes_demand_ids": ["DEM-INIT-1"], "working": "VISHWAS settlement", "rule_version": "r"},
        "DemandRaised.v1",
    )
    assert q("SELECT state, settled_by FROM demands WHERE demand_id='DEM-INIT-1'") == [("WAIVED", "DEM-VISHWAS-1")]

    # 3. Delayed bank confirmation for DEM-INIT-1 arrives out of order
    _deliver(
        on_demand_paid,
        {"payment_id": "PAY-DELAYED-1", "purpose": "DEMAND", "reference_type": "demand",
         "reference_id": "DEM-INIT-1", "amount_paise": 150000, "mock": True},
        "PaymentConfirmed.v1",
    )

    # 4. Correct end state: demand must remain WAIVED, not overwritten to PAID; no journal posted
    assert q("SELECT state, settled_by FROM demands WHERE demand_id='DEM-INIT-1'") == [("WAIVED", "DEM-VISHWAS-1")]
    assert q("SELECT COUNT(*) FROM journals WHERE business_key='PAY-DELAYED-1'")[0][0] == 0


def test_lead_2_older_payment_cannot_overwrite_withdrawn_demand(ctx):
    """Lead 2: A demand is withdrawn by compliance-service (DemandRaised.v1 with withdraw=True).
    An older/delayed payment confirmation (PaymentConfirmed.v1) arriving later
    must NOT overwrite the withdrawn demand to PAID.
    """
    _, q = ctx
    from app.infra.demands import on_demand_paid, on_demand_raised

    _deliver(
        on_demand_raised,
        {"demand_id": "DEM-WITHDRAW-TARGET", "establishment_id": EST, "demand_type": "DUES_7A",
         "amount_paise": 200000, "supersedes_demand_ids": [], "working": "[]", "rule_version": "r"},
        "DemandRaised.v1",
    )
    assert q("SELECT state FROM demands WHERE demand_id='DEM-WITHDRAW-TARGET'") == [("OPEN",)]

    # Compliance withdraws the demand
    _deliver(
        on_demand_raised,
        {"demand_id": "ORDER-WITHDRAW-1", "establishment_id": EST, "demand_type": "DUES_7A",
         "amount_paise": 0, "withdraw": True, "supersedes_demand_ids": ["DEM-WITHDRAW-TARGET"], "rule_version": "r"},
        "DemandRaised.v1",
    )
    assert q("SELECT state, settled_by FROM demands WHERE demand_id='DEM-WITHDRAW-TARGET'") == [("WITHDRAWN", "ORDER-WITHDRAW-1")]

    # Delayed bank payment arrives
    _deliver(
        on_demand_paid,
        {"payment_id": "PAY-DELAYED-WITHDRAWN", "purpose": "DEMAND", "reference_type": "demand",
         "reference_id": "DEM-WITHDRAW-TARGET", "amount_paise": 200000, "mock": True},
        "PaymentConfirmed.v1",
    )

    # Correct end state: remains WITHDRAWN
    assert q("SELECT state, settled_by FROM demands WHERE demand_id='DEM-WITHDRAW-TARGET'") == [("WITHDRAWN", "ORDER-WITHDRAW-1")]
    assert q("SELECT COUNT(*) FROM journals WHERE business_key='PAY-DELAYED-WITHDRAWN'")[0][0] == 0


def test_lead_2_late_waiver_cannot_overwrite_collected_demand(ctx):
    """Lead 2: A demand is paid directly by the employer (PaymentConfirmed.v1).
    A late waiver event from compliance (DemandRaised.v1) arriving afterwards
    must NOT mark the already collected demand WAIVED or WITHDRAWN.
    """
    _, q = ctx
    from app.infra.demands import on_demand_paid, on_demand_raised

    _deliver(
        on_demand_raised,
        {"demand_id": "DEM-COLLECTED-1", "establishment_id": EST, "demand_type": "DAMAGES_14B",
         "amount_paise": 100000, "supersedes_demand_ids": [], "working": "14B initial", "rule_version": "r"},
        "DemandRaised.v1",
    )
    # Payment confirmed first
    _deliver(
        on_demand_paid,
        {"payment_id": "PAY-COLLECTED-1", "purpose": "DEMAND", "reference_type": "demand",
         "reference_id": "DEM-COLLECTED-1", "amount_paise": 100000, "mock": True},
        "PaymentConfirmed.v1",
    )
    assert q("SELECT state, settled_by FROM demands WHERE demand_id='DEM-COLLECTED-1'") == [("PAID", "PAY-COLLECTED-1")]
    assert q("SELECT COUNT(*) FROM journals WHERE business_key='PAY-COLLECTED-1'")[0][0] == 1

    # Late waiver arrives attempting to supersede DEM-COLLECTED-1
    _deliver(
        on_demand_raised,
        {"demand_id": "DEM-LATE-WAIVER-1", "establishment_id": EST, "demand_type": "DAMAGES_14B_VISHWAS",
         "amount_paise": 30000, "supersedes_demand_ids": ["DEM-COLLECTED-1"], "working": "Late waiver", "rule_version": "r"},
        "DemandRaised.v1",
    )

    # Correct end state: demand remains PAID, not overwritten to WAIVED
    assert q("SELECT state, settled_by FROM demands WHERE demand_id='DEM-COLLECTED-1'") == [("PAID", "PAY-COLLECTED-1")]


def test_lead_2_recovery_realised_cannot_apply_to_waived_demand(ctx):
    """Lead 2: A demand waived under VISHWAS must not be modified if a RecoveryRealised.v1
    event arrives for it.
    """
    _, q = ctx
    import json as _json
    from app.infra.demands import on_demand_raised, on_recovery_realised

    dues = [{"wage_month": "2025-04", "ac1_employee_paise": 100000, "ac1_employer_paise": 50000,
             "ac10_pension_paise": 50000, "ac21_edli_paise": 0, "ac2_admin_paise": 0}]
    _deliver(
        on_demand_raised,
        {"demand_id": "DEM-7A-RECO-WAIVE", "establishment_id": EST, "demand_type": "DUES_7A",
         "amount_paise": 200000, "supersedes_demand_ids": [], "working": _json.dumps(dues), "rule_version": "r"},
        "DemandRaised.v1",
    )

    # Waive it
    _deliver(
        on_demand_raised,
        {"demand_id": "DEM-7A-REVISED", "establishment_id": EST, "demand_type": "DUES_7A",
         "amount_paise": 100000, "supersedes_demand_ids": ["DEM-7A-RECO-WAIVE"], "working": _json.dumps(dues), "rule_version": "r"},
        "DemandRaised.v1",
    )
    assert q("SELECT state FROM demands WHERE demand_id='DEM-7A-RECO-WAIVE'") == [("WAIVED",)]

    # Recovery realisation arrives for the waived demand
    _deliver(
        on_recovery_realised,
        {"recovery_case_id": "RC-W1", "establishment_id": EST, "demand_ids": ["DEM-7A-RECO-WAIVE"],
         "amount_paise": 200000, "mode": "DIRECT", "reference": "REC-WAIVED-ATTEMPT"},
        "RecoveryRealised.v1",
    )

    # Correct end state: demand remains WAIVED with realised_paise=0, no recovery journal
    assert q("SELECT state, realised_paise FROM demands WHERE demand_id='DEM-7A-RECO-WAIVE'") == [("WAIVED", 0)]
    assert q("SELECT COUNT(*) FROM journals WHERE business_key='RECOVERY-REC-WAIVED-ATTEMPT'")[0][0] == 0


# ==============================================================================
# Lead 7: transfer_legs table (detail JSON column and leg states)
# Producers: claim-service (TrustAnnexureKReconciled.v1)
#            pension-service (EpsServiceTransferred.v1)
# ==============================================================================

def test_lead_7_concurrent_transfer_legs_interleaved_lost_update(ctx):
    """Lead 7: Both TrustAnnexureKReconciled.v1 (claim-service) and EpsServiceTransferred.v1
    (pension-service) update the transfer_legs row for a Form 13 transfer.
    When executed concurrently / interleaved (both fetch detail before writing),
    neither writer's detail fields must be clobbered or lost in the end state.
    """
    client, q = ctx
    from app.infra.transfers import on_eps_service_transferred, on_process_transitioned, on_trust_annexure_k

    # 1. Setup Form 13 trust transfer
    transfer_id = "CASE-LEAD7-RACE"
    _deliver(on_process_transitioned, transition(transfer_id, "100000000912", "AL-0918", "AL-0919"), "ProcessTransitioned.v1")
    [initial_row] = q(f"SELECT pf_leg, eps_leg, detail FROM transfer_legs WHERE transfer_id='{transfer_id}'")
    assert initial_row[0] == "AWAITING_TRUST" and initial_row[1] == "WAITING_FOR_PF"

    payload_pf = {
        "annexure_id": "ANN-LEAD7",
        "transfer_id": transfer_id,
        "to_account_link_id": "AL-0919",
        "employee_paise": 120000,
        "employer_paise": 80000,
        "service_from": "2020-01-01",
        "service_to": "2026-06-30",
        "breaks_months": 2,
    }
    payload_eps = {
        "transfer_id": transfer_id,
        "from_account_link_id": "AL-0918",
        "to_account_link_id": "AL-0919",
        "service_months": 76,
        "breaks_months": 2,
    }

    # 2. Simulate concurrent execution where Worker 2 read detail before Worker 1 committed:
    # Worker 2 has the pre-Annexure-K snapshot of detail in memory.
    stale_detail = q(f"SELECT detail FROM transfer_legs WHERE transfer_id='{transfer_id}'")[0][0]

    # Worker 1 (claim-service) delivers TrustAnnexureKReconciled.v1 and commits:
    _deliver(on_trust_annexure_k, payload_pf, "TrustAnnexureKReconciled.v1")

    # Worker 2 (pension-service) delivers EpsServiceTransferred.v1 with its concurrent snapshot:
    # Hook Worker 2's read to return the stale_detail it fetched concurrently:
    real_on_eps = on_eps_service_transferred

    async def concurrent_eps_worker(session, event):
        orig_execute = session.execute

        async def hooked_execute(statement, params=None, *args, **kwargs):
            if "SELECT detail FROM transfer_legs" in str(statement):
                from unittest.mock import MagicMock
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = stale_detail
                return mock_result
            return await orig_execute(statement, params, *args, **kwargs)

        session.execute = hooked_execute
        try:
            return await real_on_eps(session, event)
        finally:
            session.execute = orig_execute

    _deliver(concurrent_eps_worker, payload_eps, "EpsServiceTransferred.v1")

    # 3. Assert correct end state:
    # Both PF leg and EPS leg must be COMPLETED.
    # CRITICAL: BOTH PF details (annexure_id, service_from, service_to) AND EPS details
    # (service_months, eps_breaks_months) must be preserved in the copy!
    [end_row] = q(f"SELECT pf_leg, eps_leg, detail, eps_detail FROM transfer_legs WHERE transfer_id='{transfer_id}'")
    assert end_row[0] == "COMPLETED"
    assert end_row[1] == "COMPLETED"

    detail = end_row[2] if isinstance(end_row[2], dict) else json.loads(end_row[2])
    eps_detail = end_row[3] if isinstance(end_row[3], dict) else json.loads(end_row[3]) if end_row[3] else {}

    # Check via office API view as well
    office = hdr("do-caseworker", "fo.da_accounts", [], establishment=None)
    shown = client.get(f"/api/v1/office/transfers/{transfer_id}/legs", headers=office).json()["data"]

    # PF detail checks: on UNCHANGED code, annexure_id was overwritten by Handler B!
    assert detail.get("annexure_id") == "ANN-LEAD7", f"Lost annexure_id in detail: {detail}"
    assert detail.get("service_from") == "2020-01-01", f"Lost service_from in detail: {detail}"
    assert detail.get("service_to") == "2026-06-30", f"Lost service_to in detail: {detail}"

    # EPS detail checks
    assert shown["eps_leg"]["detail"]["service_months"] == 76
    assert shown["eps_leg"]["detail"]["breaks_months"] == 2
    assert (eps_detail.get("service_months") or detail.get("service_months")) == 76
    assert (eps_detail.get("breaks_months") or detail.get("breaks_months")) == 2


def test_lead_7_concurrent_transfer_legs_interleaved_pf_overwrites_eps(ctx):
    """Lead 7 (reverse interleaving): Handler A (on_trust_annexure_k) reads stale detail before
    Handler B (on_eps_service_transferred) commits. Handler A writes back its detail, clobbering
    Handler B's EPS service_months and eps_breaks_months.
    """
    client, q = ctx
    from app.infra.transfers import on_eps_service_transferred, on_process_transitioned, on_trust_annexure_k

    transfer_id = "CASE-LEAD7-REV"
    _deliver(on_process_transitioned, transition(transfer_id, "100000000912", "AL-0918", "AL-0919"), "ProcessTransitioned.v1")

    payload_pf = {
        "annexure_id": "ANN-LEAD7-REV",
        "transfer_id": transfer_id,
        "to_account_link_id": "AL-0919",
        "employee_paise": 120000,
        "employer_paise": 80000,
        "service_from": "2020-01-01",
        "service_to": "2026-06-30",
        "breaks_months": 2,
    }
    payload_eps = {
        "transfer_id": transfer_id,
        "from_account_link_id": "AL-0918",
        "to_account_link_id": "AL-0919",
        "service_months": 84,
        "breaks_months": 3,
    }

    # Worker 1 reads initial stale detail
    stale_leg = dict(q(f"SELECT * FROM transfer_legs WHERE transfer_id='{transfer_id}'")[0]._mapping)

    # Worker 2 (EPS) delivers and commits first
    _deliver(on_eps_service_transferred, payload_eps, "EpsServiceTransferred.v1")

    # Worker 1 (PF) delivers with its concurrent snapshot where leg['detail'] lacked EPS fields
    real_on_pf = on_trust_annexure_k

    async def concurrent_pf_worker(session, event):
        orig_execute = session.execute

        async def hooked_execute(statement, params=None, *args, **kwargs):
            if "SELECT * FROM transfer_legs" in str(statement):
                from unittest.mock import MagicMock
                mock_result = MagicMock()
                mock_result.mappings.return_value.first.return_value = stale_leg
                return mock_result
            return await orig_execute(statement, params, *args, **kwargs)

        session.execute = hooked_execute
        try:
            return await real_on_pf(session, event)
        finally:
            session.execute = orig_execute

    _deliver(concurrent_pf_worker, payload_pf, "TrustAnnexureKReconciled.v1")

    # Assert end state:
    [end_row] = q(f"SELECT pf_leg, eps_leg, detail, eps_detail FROM transfer_legs WHERE transfer_id='{transfer_id}'")
    assert end_row[0] == "COMPLETED"
    assert end_row[1] == "COMPLETED"

    detail = end_row[2] if isinstance(end_row[2], dict) else json.loads(end_row[2])
    eps_detail = end_row[3] if isinstance(end_row[3], dict) else json.loads(end_row[3]) if end_row[3] else {}
    office = hdr("do-caseworker", "fo.da_accounts", [], establishment=None)
    shown = client.get(f"/api/v1/office/transfers/{transfer_id}/legs", headers=office).json()["data"]

    # Both sets of details must be preserved
    assert detail.get("annexure_id") == "ANN-LEAD7-REV"
    assert shown["eps_leg"]["detail"]["service_months"] == 84, f"Lost service_months in eps_leg: {shown}"
    assert shown["eps_leg"]["detail"]["breaks_months"] == 3
    assert (eps_detail.get("service_months") or detail.get("service_months")) == 84
    assert (eps_detail.get("breaks_months") or detail.get("breaks_months")) == 3

