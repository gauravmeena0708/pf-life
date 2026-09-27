"""Tier-2 process engine (ADR-0005) running the member_freeze definition from config/processes."""
import json

from tests.test_cases_api import S, ctx, hdr, queue  # noqa: F401  (ctx is a fixture)

RPFC, DA, SS, APFC, OIC = S["zo-rpfc"], S["do-caseworker"], S["ro-ss"], S["ro-apfc"], S["ro-oic"]
UAN = "100000000002"
FORM = {"category": "B", "reason": "Suspicious change of bank details reported", "order_ref": "ORD-DEMO-1"}
CHAIN = ((DA, "fo.da_accounts"), (SS, "fo.ss"), (APFC, "fo.apfc"), (OIC, "fo.oic"))


def freeze(client, subject=RPFC, role="zo.rpfc1", uan=UAN, form=FORM, step=True):
    return client.post(f"/api/v1/office/members/{uan}/freezes", json=form,
                       headers=hdr(subject, role, {"action": "freeze-account", "resource_id": uan} if step else None))


def verify(client, case_id, subject, role, finding="GENUINE_MEMBER"):
    return client.post(f"/api/v1/office/freeze-cases/{case_id}/verifications",
                       json={"finding": finding, "note": "Checked the member ledger and KYC"}, headers=hdr(subject, role))


def defreeze(client, subject=OIC, uan=UAN):
    return client.post(f"/api/v1/office/members/{uan}/defreezes", json={"reason": "Member verified in person at the RO"},
                       headers=hdr(subject, "fo.oic", {"action": "defreeze-account", "resource_id": uan}))


def transitions(q):
    return [(p["from_state"], p["to_state"], p["operation"]) for p in
            ((json.loads(x) if isinstance(x, str) else x)["envelope"]["payload"]
             for (x,) in q("SELECT payload FROM outbox WHERE event_type='ProcessTransitioned.v1' ORDER BY id"))]


def test_freeze_verify_through_the_chain_then_defreeze(ctx):
    client, q, _ = ctx
    r = freeze(client)
    assert r.status_code == 200, r.json()
    case = r.json()["data"]
    assert case["state"] == "FROZEN" and case["chain"] == ["fo.da_accounts", "fo.ss", "fo.apfc", "fo.oic"]
    [queued] = queue(client, DA, "fo.da_accounts")
    assert queued["process"] == "member_freeze" and queued["next_action"] == "verify" and queued["subject_ref"] == UAN
    for subject, role in CHAIN:
        assert verify(client, case["case_id"], subject, role).status_code == 200
    [queued] = queue(client, OIC, "fo.oic")
    assert queued["next_action"] == "defreeze"
    r = defreeze(client)
    assert r.status_code == 200 and r.json()["data"]["state"] == "ACTIVE"
    assert queue(client, OIC, "fo.oic") == []
    assert transitions(q) == [(None, "FROZEN", "freeze"), ("FROZEN", "VERIFIED", "verify"), ("VERIFIED", "ACTIVE", "defreeze")]


def test_chain_order_one_step_per_officer_and_no_early_defreeze(ctx):
    client, _, _ = ctx
    case = freeze(client).json()["data"]
    assert verify(client, case["case_id"], SS, "fo.ss").status_code == 403           # out of order
    assert verify(client, case["case_id"], DA, "fo.da_accounts").status_code == 200
    assert verify(client, case["case_id"], DA, "fo.da_accounts").status_code == 403  # not DA's turn any more
    assert defreeze(client).status_code == 409                                       # verification not finished


def test_the_freezing_officer_cannot_verify_their_own_order(ctx):
    client, _, _ = ctx
    case = freeze(client, subject=APFC, role="fo.apfc").json()["data"]               # the RO APFC orders the freeze
    for subject, role in CHAIN[:2]:
        assert verify(client, case["case_id"], subject, role).status_code == 200
    r = verify(client, case["case_id"], APFC, "fo.apfc")
    assert r.status_code == 403 and r.json()["type"] == "/problems/separation-of-duties"


def test_step_up_form_role_and_jurisdiction(ctx):
    client, _, _ = ctx
    assert freeze(client, step=False).status_code == 428
    wrong = client.post(f"/api/v1/office/members/{UAN}/freezes", json=FORM,
                        headers=hdr(RPFC, "zo.rpfc1", {"action": "freeze-account", "resource_id": "100000000001"}))
    assert wrong.status_code == 403                                                  # step-up for another UAN
    assert freeze(client, form={**FORM, "category": "Z"}).status_code == 422
    assert freeze(client, subject=SS, role="fo.ss").status_code == 403
    assert freeze(client, uan="999999999999").status_code == 404                    # not a subject of this office
    assert freeze(client).status_code == 200
    assert freeze(client).status_code == 409                                         # already frozen


def test_suspected_fraud_cannot_be_defrozen(ctx):
    client, _, _ = ctx
    case = freeze(client).json()["data"]
    for subject, role in CHAIN[:-1]:
        verify(client, case["case_id"], subject, role)
    verify(client, case["case_id"], OIC, "fo.oic", finding="SUSPECTED_FRAUD")
    r = defreeze(client)
    assert r.status_code == 409 and r.json()["type"] == "/problems/finding-required"
