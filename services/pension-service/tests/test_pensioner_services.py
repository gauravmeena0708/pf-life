"""Life certificates, suspension and resumption (held months released), office updation activities (DA initiates,
APFC settles), pensioner self-service and the public enquiries."""
import hashlib
import hmac
from datetime import date

from tests.test_pensions import APFC_P, PENSIONER, SUBJECTS, ctx, hdr  # noqa: F401  (ctx is a fixture)

DA_P = SUBJECTS["ro-da-pension"]


def at(monkeypatch, day: date) -> None:
    """Move the service's clock: the pension is credited on the last day of each month."""
    import app.api.family_routes as f
    import app.api.services_routes as r
    import app.api.settlement_routes as w
    import app.domain.pension as p
    import app.domain.services as s
    for module in (p, s, r, w, f):
        monkeypatch.setattr(module, "today", lambda: day)


def test_lapsed_certificate_suspends_and_a_physical_one_resumes_with_held_months(ctx, monkeypatch):
    client, _, _ = ctx
    at(monkeypatch, date(2026, 9, 28))
    overdue = client.get("/api/v1/office/pensions/life-certificates/overdue", headers=hdr(APFC_P, "fo.apfc_pension")).json()["data"]
    assert [o["ppo_id"] for o in overdue] == ["PPO-DEMO-0002"]
    body = {"reason": "No life certificate since 31 August"}
    refused = client.post("/api/v1/office/pensions/PPO-DEMO-0001/suspensions", json=body,
                          headers=hdr(APFC_P, "fo.apfc_pension", {"action": "suspend-pension", "resource_id": "PPO-DEMO-0001"}))
    assert refused.json()["type"] == "/problems/life-certificate-valid"
    done = client.post("/api/v1/office/pensions/PPO-DEMO-0002/suspensions", json=body,
                       headers=hdr(APFC_P, "fo.apfc_pension", {"action": "suspend-pension", "resource_id": "PPO-DEMO-0002"}))
    assert done.status_code == 200 and done.json()["data"]["status"] == "SUSPENDED"

    at(monkeypatch, date(2026, 11, 10))                              # September and October are not credited meanwhile
    enquiry = client.get("/api/v1/office/pensions/enquiries?ppo=PPO-DEMO-0002", headers=hdr(DA_P, "fo.da_pension")).json()["data"]
    months = {p["month"] for p in enquiry["pension_payment_details"]}
    assert "2026-08" in months and "2026-09" not in months and enquiry["ppo_details"]["status"] == "SUSPENDED"
    assert set(enquiry) >= {"ppo_details", "beneficiary_details", "pension_payment_details", "scheme_certificate_issue_details",
                            "service_details", "arrears_adjustment_details", "recovery_details", "tds_details"}
    step = {"action": "initiate-pension-updation", "resource_id": "PPO-DEMO-0002"}
    act = client.post("/api/v1/office/pensions/PPO-DEMO-0002/updation-activities",
                      json={"activity": "PHYSICAL_LC", "mode": "PHYSICAL", "reason": "Life certificate given at the PRO counter"},
                      headers=hdr(DA_P, "fo.da_pension", step)).json()["data"]
    assert act["status"] == "PENDING"
    url = f"/api/v1/office/pensions/updation-activities/{act['activity_id']}/decisions"
    decision = {"decision": "SETTLE", "note": "Certificate seen"}
    assert client.post(url, json=decision, headers=hdr(DA_P, "fo.da_pension")).status_code == 403            # the DA cannot settle
    settled = client.post(url, json=decision, headers=hdr(APFC_P, "fo.apfc_pension", {"action": "decide-pension-updation", "resource_id": act["activity_id"]}))
    assert settled.status_code == 200 and settled.json()["data"]["status"] == "SETTLED"
    enquiry = client.get("/api/v1/office/pensions/enquiries?ppo=PPO-DEMO-0002", headers=hdr(DA_P, "fo.da_pension")).json()["data"]
    released = [p for p in enquiry["pension_payment_details"] if p["month"] in ("2026-09", "2026-10")]
    assert {p["paid_on"] for p in released} == {"2026-11-10"}                                # held months paid on resumption
    assert enquiry["ppo_details"]["status"] == "IN_PAYMENT" and enquiry["ppo_details"]["life_certificate"]["state"] == "VALID"
    tracker = client.get("/api/v1/office/pensions/updation-activities?status=SETTLED", headers=hdr(DA_P, "fo.da_pension")).json()["data"]
    assert tracker[0]["activity"] == "PHYSICAL_LC" and "valid till" in tracker[0]["decision_note"]


def test_pensioner_self_service_dlc_bank_change_and_declarations(ctx):
    client, _, _ = ctx
    me = hdr(PENSIONER, "pensioner")
    ppo = client.get("/api/v1/pensioners/me/ppo", headers=me).json()["data"]
    assert ppo["ppo_id"] == "PPO-DEMO-0001" and ppo["disbursing_bank"]["account_last4"] == "0901"
    slip = client.get("/api/v1/pensioners/me/pension-slips?month=2026-08", headers=me).json()["data"]
    assert slip["gross_paise"] == slip["net_paise"] == 111400
    dlc = client.post("/api/v1/pensioners/me/life-certificate/submissions", json={"face_authentication_consent": True}, headers=me).json()["data"]
    assert dlc["mock"] is True and client.get("/api/v1/pensioners/me/life-certificate", headers=me).json()["data"]["reference"] == dlc["pramaan_id"]
    bank = {"ifsc": "DEMO0000999", "account_number": "123456789999"}
    assert client.post("/api/v1/pensioners/me/bank-change-requests", json=bank, headers=me).status_code == 428
    req = client.post("/api/v1/pensioners/me/bank-change-requests", json=bank,
                      headers=hdr(PENSIONER, "pensioner", {"action": "change-pension-bank", "resource_id": "PPO-DEMO-0001"})).json()["data"]
    client.post(f"/api/v1/office/pensions/updation-activities/{req['activity_id']}/decisions", json={"decision": "SETTLE", "note": "Bank letter checked"},
                headers=hdr(APFC_P, "fo.apfc_pension", {"action": "decide-pension-updation", "resource_id": req["activity_id"]}))
    assert client.get("/api/v1/pensioners/me/ppo", headers=me).json()["data"]["disbursing_bank"]["account_last4"] == "9999"
    d = client.post("/api/v1/pensioners/me/declarations", json={"kind": "NON_EMPLOYMENT", "declared": True}, headers=me).json()["data"]
    assert "NON_EMPLOYMENT" in d["declarations"]
    sig = hmac.new(b"dev-mock-jeevan-pramaan", f"{dlc['pramaan_id']}|PPO-DEMO-0001|ACCEPTED".encode(), hashlib.sha256).hexdigest()
    anyone = hdr("anonymous", "public")
    assert client.post("/api/v1/integrations/mock-jeevan-pramaan/dlc-events", json={"pramaan_id": dlc["pramaan_id"], "ppo_id": "PPO-DEMO-0001",
                       "status": "ACCEPTED", "signature": "0" * 64}, headers=anyone).status_code == 401
    assert client.post("/api/v1/integrations/mock-jeevan-pramaan/dlc-events", json={"pramaan_id": dlc["pramaan_id"], "ppo_id": "PPO-DEMO-0001",
                       "status": "ACCEPTED", "signature": sig}, headers=anyone).status_code == 200


def test_public_enquiries_disclose_little(ctx):
    client, _, _ = ctx
    anyone = hdr("anonymous", "public")
    found = client.post("/api/v1/public/pension/ppo-lookups", json={"uan": "100000000901", "date_of_birth": "1965-05-10"}, headers=anyone).json()["data"]
    assert found == {"found": True, "ppo_id": "PPO-DEMO-0001", "office_id": "RO-DEMO-01", "name": "G**** D***", "label": "SYNTHETIC_DEMO"}
    assert client.post("/api/v1/public/pension/ppo-lookups", json={"uan": "100000000901", "date_of_birth": "1965-05-11"}, headers=anyone).json()["data"]["found"] is False
    pay = client.post("/api/v1/public/pension/payment-enquiries", json={"ppo_id": "PPO-DEMO-0001", "date_of_birth": "1965-05-10"}, headers=anyone).json()["data"]
    assert pay["found"] and "amount_paise" not in str(pay["months"])
    status = client.post("/api/v1/public/pension/status-enquiries", json={"ppo_id": "PPO-DEMO-0002"}, headers=anyone).json()["data"]
    assert status["pension_status"] == "Active" and status["life_certificate_due"] == "2026-08-31"
    lc = client.post("/api/v1/public/pension/life-certificate-lookups", json={"ppo_id": "PPO-DEMO-0002"}, headers=anyone).json()["data"]
    assert lc == {"found": True, "state": "EXPIRED", "valid_till_month": "2026-08", "label": "SYNTHETIC_DEMO"}


def test_a_pension_updation_inwarded_at_the_pro_counter_lands_on_the_tracker(ctx):
    import asyncio
    import uuid

    import app.infra.db as db
    from app.infra.messaging import dispatch
    from epfo_persistence.consumer import apply_once
    client, _, _ = ctx
    payload = {"intake_id": "INW-0001", "form_type": "PHYSICAL_LC_UPDATION", "uan": "100000000001", "ppo_id": "PPO-DEMO-0002",
               "office_id": "RO-DEMO-01", "filed_by": "PENSIONER", "details": {"certificate_signed_by": "Bank manager"}}
    event = {"event_id": str(uuid.uuid4()), "event_type": "PhysicalClaimInwarded.v1", "producer": "claim-service",
             "correlation_id": str(uuid.uuid4()), "payload": payload}
    assert asyncio.run(apply_once(db.sessions(), event, dispatch))
    asyncio.run(apply_once(db.sessions(), {**event, "event_id": str(uuid.uuid4())}, dispatch))       # re-sent: still one activity
    new = client.get("/api/v1/office/pensions/updation-activities?status=NEW", headers=hdr(DA_P, "fo.da_pension")).json()["data"]
    assert [(a["activity"], a["mode"], a["initiated_role"]) for a in new] == [("PHYSICAL_LC", "PHYSICAL", "fo.pro_intake")]
