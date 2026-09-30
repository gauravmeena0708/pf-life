"""Phase 2, slice 8c: the EDLI section verifies the average wages of an admitted Form 5IF claim and decides; the
benefit is worked out again from the claim's rules with those wages, and the confirmation is bound to it."""
from tests.test_claims_api import SUBJECTS, ctx, events, hdr  # noqa: F401
from tests.test_death_claims import approve, file

EDLI = SUBJECTS["ro-edli"]


def admitted(client, deliver):
    c = file(client, "FORM_5IF").json()["data"]
    approve(deliver, c["claim_id"])
    return c


def preview(client, claim_id, wages):
    return client.post(f"/api/v1/office/edli-claims/{claim_id}/benefit-previews", json={"average_monthly_wages_paise": wages},
                       headers=hdr(EDLI, "fo.edli"))


def test_the_edli_section_sees_admitted_claims_only(ctx):
    client, _, deliver = ctx
    c = file(client, "FORM_5IF").json()["data"]
    assert client.get("/api/v1/office/edli-claims", headers=hdr(EDLI, "fo.edli")).json()["data"] == []
    assert preview(client, c["claim_id"], 1500000).status_code == 409                       # not admitted yet
    approve(deliver, c["claim_id"])
    [item] = client.get("/api/v1/office/edli-claims", headers=hdr(EDLI, "fo.edli")).json()["data"]
    assert item["claim_id"] == c["claim_id"] and item["death_of_uan"] == "100000000901"
    assert client.get("/api/v1/office/edli-claims", headers=hdr(SUBJECTS["ro-ao"], "fo.ao")).status_code == 403


def test_verified_wages_change_the_benefit_and_the_confirmation_is_bound_to_it(ctx):
    client, q, deliver = ctx
    c = admitted(client, deliver)
    low, high = preview(client, c["claim_id"], 1000000).json()["data"], preview(client, c["claim_id"], 1500000).json()["data"]
    assert low["amount_paise"] < high["amount_paise"] and "x 35" in high["working"]
    url = f"/api/v1/office/edli-claims/{c['claim_id']}/decisions"
    body = {"decision": "APPROVE", "average_monthly_wages_paise": 1000000, "reason": "Wages verified on the employer certificate"}
    wrong = {"action": "decide-edli", "resource_id": c["claim_id"], "resource_version": high["version"], "amount_paise": high["amount_paise"]}
    assert client.post(url, json=body, headers=hdr(EDLI, "fo.edli", wrong)).status_code == 403     # confirmed a different amount
    step = {**wrong, "amount_paise": low["amount_paise"]}
    r = client.post(url, json=body, headers=hdr(EDLI, "fo.edli", step)).json()["data"]
    assert r["state"] == "APPROVED" and r["amount_paise"] == low["amount_paise"]
    [decision] = events(q, "ClaimDecisionRecorded.v1")
    assert decision["fund"] == "EDLI" and decision["amount_paise"] == low["amount_paise"] and decision["reason_code"] == "EDLI_SANCTIONED"
    assert client.post(url, json=body, headers=hdr(EDLI, "fo.edli", step)).status_code == 409


def test_the_edli_section_can_reject_with_a_reason(ctx):
    client, q, deliver = ctx
    c = admitted(client, deliver)
    version = preview(client, c["claim_id"], 1500000).json()["data"]["version"]
    r = client.post(f"/api/v1/office/edli-claims/{c['claim_id']}/decisions",
                    json={"decision": "REJECT", "reason": "The member was not in service on the date of death"},
                    headers=hdr(EDLI, "fo.edli", {"action": "decide-edli", "resource_id": c["claim_id"], "resource_version": version}))
    assert r.json()["data"]["state"] == "REJECTED_WITH_REASON"
    assert events(q, "ClaimDecisionRecorded.v1")[0]["decision"] == "REJECTED"
