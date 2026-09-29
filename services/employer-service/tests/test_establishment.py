"""Phase 2, slice 6a: the establishment's record (KYC, branches, Form 5A, contractors, bank accounts, exemption),
changes the office decides, and OLRE — DA Compliance scrutiny then the APFC's coverage decision."""
from tests.test_employer_api import EST, SUBJECTS, api, owner, token  # noqa: F401  (api is a fixture)

DA_C, APFC, OPERATOR = SUBJECTS["ro-da-compliance"], SUBJECTS["ro-apfc"], SUBJECTS["emp-preparer"]


def office(subject, role, step_up=None):
    return token(subject, role, establishment=None, step_up=step_up)


def test_kyc_through_the_mock_registry_and_the_read_only_views(api):
    kyc = api.get("/api/v1/employers/me/kyc", headers=owner()).json()["data"]["kyc"]
    assert kyc["PAN"]["status"] == "VERIFIED" and kyc["PAN"]["value"].endswith("000D") and kyc["TAN"]["status"] == "NOT_SEEDED"
    url, step = "/api/v1/employers/me/kyc/TAN", {"action": "seed-establishment-kyc", "resource_id": f"{EST}:TAN"}
    assert api.post(url, json={"value": "DELD12345A"}, headers=owner()).status_code == 428
    assert api.post(url, json={"value": "bad"}, headers=owner(step)).status_code in (400, 422)
    bad = api.post(url, json={"value": "DELD00000A"}, headers=owner(step)).json()["data"]
    assert bad["result"] == "REJECTED"
    ok = api.post(url, json={"value": "DELD12345A"}, headers=owner(step)).json()["data"]
    assert ok["result"] == "VERIFIED" and ok["mock"] is True
    assert api.get("/api/v1/employers/me/kyc", headers=owner()).json()["data"]["kyc"]["TAN"]["status"] == "VERIFIED"
    assert api.get("/api/v1/employers/me/bank-accounts", headers=owner()).json()["data"][0]["account_last4"] == "0100"
    assert api.get("/api/v1/employers/me/exemption", headers=owner()).json()["data"]["exempted"] is False


def test_branches_form_5a_and_contractors(api):
    body = {"name": "Weaving unit, Panipat", "kind": "BRANCH", "address": {"line": "Plot 3", "city": "Panipat", "district": "Panipat", "pincode": "132103"}}
    b = api.post("/api/v1/employers/me/branches", json=body, headers=owner())
    assert b.status_code == 201 and b.json()["data"]["sub_code"].endswith("/001")
    assert api.get("/api/v1/employers/me/configuration", headers=owner()).json()["data"]["sub_codes"] == [b.json()["data"]["sub_code"]]
    assert api.get("/api/v1/employers/me/ownership-declaration", headers=owner()).json()["data"]["filed"] is False
    form = {"nature_of_business": "Textile manufacturing", "persons": [
        {"name": "Ravi Demo", "designation": "Director", "role": "DIRECTOR", "pan": "ABCPD1234E", "share_pct": 60},
        {"name": "Sita Demo", "designation": "Director", "role": "DIRECTOR", "pan": "ABCPD1235F", "share_pct": 50}]}
    step = {"action": "sign-form-5a", "resource_id": EST}
    assert api.put("/api/v1/employers/me/ownership-declaration", json=form, headers=owner(step)).status_code == 422   # 110 %
    form["persons"][1]["share_pct"] = 40
    assert api.put("/api/v1/employers/me/ownership-declaration", json=form, headers=owner()).status_code == 428
    filed = api.put("/api/v1/employers/me/ownership-declaration", json=form, headers=owner(step)).json()["data"]
    assert filed["version"] == 1 and filed["persons"][0]["pan"] == "******234E"
    again = api.put("/api/v1/employers/me/ownership-declaration", json=form, headers=owner(step)).json()["data"]
    assert again["version"] == 2
    c = {"registration_number": "DEMO/00099/000", "name": "Demo Security Services", "work_order_ref": "WO/2026/14", "valid_from": "2026-04-01"}
    linked = api.post("/api/v1/employers/me/contractors", json=c, headers=owner())
    assert linked.status_code == 201 and linked.json()["data"]["registered_with_epfo"] is False
    assert len(api.get("/api/v1/employers/me/contractors", headers=owner()).json()["data"]) == 1
    op = token(OPERATOR, "employer.operator", ["ecr.prepare"])
    assert api.post("/api/v1/employers/me/contractors", json=c, headers=op).status_code == 403


def test_address_change_is_a_request_the_office_decides(api):
    step = {"action": "request-establishment-change", "resource_id": EST}
    body = {"address": {"line": "Plot 9, New Industrial Area", "city": "New Delhi", "district": "Central Delhi", "pincode": "110002"},
            "reason": "Moved to a new factory building"}
    assert api.patch("/api/v1/employers/me", json=body, headers=owner()).status_code == 428
    r = api.patch("/api/v1/employers/me", json=body, headers=owner(step))
    assert r.status_code == 200 and r.json()["data"]["state"] == "PENDING" and r.json()["data"]["changes"]["pincode"]["to"] == "110002"
    assert api.patch("/api/v1/employers/me", json=body, headers=owner(step)).status_code == 409          # one at a time
    cfg = api.post("/api/v1/employers/me/configuration/change-requests",
                   json={"field": "establishment_type", "value": "LLP", "reason": "Converted to an LLP in 2026"}, headers=owner(step))
    assert cfg.status_code == 201
    [first, *_] = api.get("/api/v1/office/establishment-change-requests", headers=office(APFC, "fo.apfc")).json()["data"]
    assert first["legal_name"]
    url = f"/api/v1/office/establishments/{EST}/change-requests/{r.json()['data']['request_id']}/decisions"
    decision = {"decision": "APPROVE", "note": "Rent deed checked"}
    assert api.post(url, json=decision, headers=office(APFC, "fo.apfc")).status_code == 428
    done = api.post(url, json=decision, headers=office(APFC, "fo.apfc", {"action": "decide-establishment-change",
                                                                        "resource_id": r.json()["data"]["request_id"]}))
    assert done.json()["data"]["state"] == "APPROVED"
    conf = api.get("/api/v1/employers/me/configuration", headers=owner()).json()["data"]
    assert conf["address"]["pincode"] == "110002" and conf["establishment_type"] != "LLP"      # the other request is still pending


def test_olre_scrutiny_then_coverage(api):
    reg = api.post("/api/v1/employers/registration-requests", json={"legal_name": "Demo Foods LLP", "pan": "AAAFD1234K"}, headers=owner()).json()["data"]
    assert api.post(f"/api/v1/employers/registration-requests/{reg['request_id']}/verification-evidence",
                    json={"pan": "AAAFD1234K"}, headers=owner()).json()["data"]["state"] == "VERIFIED"
    listed = api.get("/api/v1/office/establishment-registrations", headers=office(DA_C, "fo.da_compliance")).json()["data"]
    row = next(x for x in listed if x["request_id"] == reg["request_id"])
    assert row["stage"] == "AWAITING_SCRUTINY"
    docs = api.get(f"/api/v1/office/establishment-registrations/{reg['request_id']}/documents", headers=office(DA_C, "fo.da_compliance")).json()["data"]
    assert docs["documents"][0]["type"] == "PAN"
    url = f"/api/v1/office/establishment-registrations/{reg['request_id']}"
    cover = {"decision": "COVER", "coverage_date": "2026-09-01", "coverage_type": "STATUTORY", "reason": "Twenty or more employees on the rolls"}
    step = {"action": "decide-coverage", "resource_id": reg["request_id"]}
    assert api.post(f"{url}/coverage-decisions", json=cover, headers=office(APFC, "fo.apfc", step)).json()["type"] == "/problems/scrutiny-pending"
    s = api.post(f"{url}/scrutiny-notes", json={"checks": ["PAN verified"], "note": "Documents in order; e-file opened"},
                 headers=office(DA_C, "fo.da_compliance")).json()["data"]
    assert s["stage"] == "SCRUTINISED" and s["efile_no"].startswith("EFILE/RO-DEMO-01/COMP/")
    assert api.post(f"{url}/scrutiny-notes", json={"checks": ["PAN verified"], "note": "Documents in order; e-file opened"},
                    headers=office(APFC, "fo.apfc")).status_code == 403                                  # the DA scrutinises
    assert api.post(f"{url}/coverage-decisions", json=cover, headers=office(APFC, "fo.apfc")).status_code == 428
    done = api.post(f"{url}/coverage-decisions", json=cover, headers=office(APFC, "fo.apfc", step)).json()["data"]
    assert done["stage"] == "COVERAGE_DECIDED" and done["coverage"]["coverage_date"] == "2026-09-01"
    assert api.post(f"{url}/coverage-decisions", json=cover, headers=office(APFC, "fo.apfc", step)).status_code == 409
