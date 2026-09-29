"""Phase 2, slice 5c: ledger locks (held by an open case, orphaned when the owner is gone, released by the OIC
with a reason) and the establishment freeze with a maker-checker de-freeze."""
import json

from tests.test_cases_api import AMOUNT, S, ctx, decide, hdr, recommend, submitted  # noqa: F401  (ctx is a fixture)

DA, SS, APFC, OIC, RPFC = S["do-caseworker"], S["ro-ss"], S["ro-apfc"], S["ro-oic"], S["zo-rpfc"]
EST = "EST-DEMO-0001"


def events(q, event_type):
    return [(json.loads(x) if isinstance(x, str) else x)["envelope"]["payload"]
            for (x,) in q(f"SELECT payload FROM outbox WHERE event_type='{event_type}' ORDER BY id")]


def locks(client, uan, subject=OIC, role="fo.oic"):
    return client.get(f"/api/v1/office/members/{uan}/locks", headers=hdr(subject, role))


def test_an_open_claim_case_holds_the_ledger_and_lets_go_when_it_finishes(ctx):
    client, _, deliver = ctx
    submitted(deliver)                                                     # AL-0001 → UAN …001
    [held] = locks(client, "100000000001").json()["data"]["active"]
    assert held["status"] == "HELD" and held["lock_scope"] == "CLAIM_ADJUDICATION" and held["resource_key"] == "AL-0001"
    release = client.post(f"/api/v1/office/system/locks/{held['lock_id']}/release", json={"reason": "Trying to release a live lock"},
                          headers=hdr(OIC, "fo.oic", {"action": "release-lock", "resource_id": held["lock_id"]}))
    assert release.json()["type"] == "/problems/lock-in-use"
    case = client.get("/api/v1/office/work-queue", headers=hdr(DA, "fo.da_accounts")).json()["data"]["items"][0]
    assert recommend(client, case).status_code == 200                      # its own lock does not block it
    case = client.get(f"/api/v1/office/cases/{case['case_id']}", headers=hdr(SS, "fo.ss")).json()["data"]
    assert decide(client, case, SS, "fo.ss", "REJECT", "Documents do not match").status_code == 200
    body = locks(client, "100000000001").json()["data"]
    assert body["active"] == [] and "finished" in body["recently_released"][0]["release_reason"]


def test_an_orphaned_lock_blocks_decisions_until_the_oic_releases_it(ctx):
    client, q, deliver = ctx
    [orphan] = locks(client, "100000000005").json()["data"]["active"]     # seeded: a dead annual-accounts batch
    assert orphan["status"] == "ORPHANED" and orphan["owner_ref"] == "BATCH-ANNUAL-2025-26"
    deliver("ClaimSubmitted.v1", {"claim_id": "CLM-E", "form_type": "31", "amount_paise": AMOUNT, "rule_version": "demo-rules-2026.1",
                                  "office_id": "RO-DEMO-01", "account_link_id": "AL-0005", "route": "REVIEW", "advisory_signal_id": None})
    case = next(c for c in client.get("/api/v1/office/work-queue", headers=hdr(DA, "fo.da_accounts")).json()["data"]["items"] if c["claim_id"] == "CLM-E")
    blocked = recommend(client, case)
    assert blocked.status_code == 409 and blocked.json()["type"] == "/problems/ledger-locked"
    url = f"/api/v1/office/system/locks/{orphan['lock_id']}/release"
    body = {"reason": "Batch run 2025-26 confirmed dead with the NDC; nothing pending on this ledger"}
    assert client.post(url, json=body, headers=hdr(APFC, "fo.apfc")).status_code == 403            # the OIC releases
    assert client.post(url, json=body, headers=hdr(OIC, "fo.oic")).status_code == 428
    assert client.post(url, json={"reason": "short"}, headers=hdr(OIC, "fo.oic", {"action": "release-lock", "resource_id": orphan["lock_id"]})).status_code == 400
    done = client.post(url, json=body, headers=hdr(OIC, "fo.oic", {"action": "release-lock", "resource_id": orphan["lock_id"]}))
    assert done.status_code == 200 and done.json()["data"]["released_by"] == OIC
    assert events(q, "LockReleased.v1")[0]["lock_scope"] == "ANNUAL_ACCOUNTING"
    assert recommend(client, case).status_code == 200


def test_establishment_freeze_and_maker_checker_defreeze(ctx):
    client, q, _ = ctx
    form = {"category": "B", "reason": "Ghost members reported by the FIA vertical", "order_ref": "ZO/FIA/2026/7"}
    url = f"/api/v1/office/establishments/{EST}/freezes"
    assert client.post(url, json=form, headers=hdr(RPFC, "zo.rpfc1")).status_code == 428
    r = client.post(url, json=form, headers=hdr(RPFC, "zo.rpfc1", {"action": "freeze-establishment", "resource_id": EST}))
    assert r.status_code == 200 and r.json()["data"]["state"] == "FROZEN", r.json()
    assert client.post(url, json=form, headers=hdr(RPFC, "zo.rpfc1", {"action": "freeze-establishment", "resource_id": EST})).status_code == 409
    step = {"action": "defreeze-establishment", "resource_id": EST}
    defreeze = f"/api/v1/office/establishments/{EST}/defreezes"
    body = {"reason": "Members verified by the enforcement officer"}
    assert client.post(defreeze, json=body, headers=hdr(OIC, "fo.oic", step)).status_code == 403    # the APFC recommends first
    made = client.post(defreeze, json=body, headers=hdr(APFC, "fo.apfc", step)).json()["data"]
    assert made["state"] == "FROZEN" and made["current_role"] == "fo.oic"
    done = client.post(defreeze, json=body, headers=hdr(OIC, "fo.oic", step)).json()["data"]
    assert done["state"] == "ACTIVE"
    assert [(p["process"], p["to_state"]) for p in events(q, "ProcessTransitioned.v1")] == [
        ("establishment_freeze", "FROZEN"), ("establishment_freeze", "ACTIVE")]
