"""Joint higher-pension options, wage-based dues and employer confirmation."""
import json

import jwt
import pytest

from tests.conftest import KEY, KID
from tests.test_pensions import SEED, SUBJECTS, ctx, hdr as pension_hdr  # noqa: F401 (ctx is a fixture)

EST = "EST-DEMO-0001"
UAN = "100000000906"
MEMBER = SUBJECTS["member-h"]
MEMBER_BASE = "/api/v1/members/me/higher-pension-options"
EMPLOYER_BASE = "/api/v1/employers/me/higher-pension-options"
WAGES = "2014-09,40000\n2014-10,40000\n2015-01,12000"
DUES = sum(max(0, wage * 100 - 1500000) * 833 // 10000 for wage in (40000, 40000, 12000))


def hdr(subject, stakeholder, step_up=None, establishment=None):
    """Reuse the pension JWT helper, adding the employer's establishment claim."""
    headers = pension_hdr(subject, stakeholder, step_up)
    if establishment:
        claims = jwt.decode(headers["Authorization"].split()[1], KEY.public_key(), algorithms=["EdDSA"], audience="pension-service")
        claims["establishment_id"] = establishment
        headers = {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}
    return headers


def employer(step_up=None, establishment=EST):
    return hdr(SUBJECTS["emp-signatory"], "employer.signatory", step_up, establishment)


def option_body(higher_from="2014-09"):
    return {"higher_wages_from": higher_from, "declaration": True, "consent_to_dues_adjustment": True}


def submit(client, higher_from="2014-09"):
    response = client.post(MEMBER_BASE, json=option_body(higher_from),
                           headers=hdr(MEMBER, "member", {"action": "submit-higher-pension-option", "resource_id": UAN}))
    assert response.status_code == 201, response.text
    return response.json()["data"]


def validation_body(wages=WAGES):
    return {"decision": "VALIDATE", "wages": wages, "note": "Payroll records verified"}


def test_eligible_member_submits_once_and_both_parties_can_read(ctx):
    client, q, _ = ctx
    body = option_body()
    assert client.post(MEMBER_BASE, json=body, headers=hdr(MEMBER, "member")).status_code == 428
    for step in ({"action": "wrong-action", "resource_id": UAN},
                 {"action": "submit-higher-pension-option", "resource_id": "100000000001"}):
        assert client.post(MEMBER_BASE, json=body, headers=hdr(MEMBER, "member", step)).status_code == 403
    assert q("SELECT COUNT(*) FROM higher_pension_options") == [(0,)]
    option = submit(client)
    assert option["state"] == "SUBMITTED" and option["uan"] == UAN
    assert option["account_link_id"] == "AL-0907" and option["higher_wages_from"] == "2014-09"
    duplicate = client.post(MEMBER_BASE, json=body,
                            headers=hdr(MEMBER, "member", {"action": "submit-higher-pension-option", "resource_id": UAN}))
    assert duplicate.status_code == 422 and "already opted" in duplicate.json()["detail"]
    assert q("SELECT COUNT(*) FROM higher_pension_options") == [(1,)]
    listed = client.get(MEMBER_BASE, headers=hdr(MEMBER, "member"))
    assert listed.status_code == 200 and listed.json()["data"]["options"] == [option]
    one = client.get(f"{MEMBER_BASE}/{option['option_id']}", headers=hdr(MEMBER, "member"))
    assert one.status_code == 200 and one.json()["data"] == option
    employers = client.get(EMPLOYER_BASE, headers=employer())
    assert employers.status_code == 200, employers.text
    [entry] = employers.json()["data"]
    assert entry["option_id"] == option["option_id"] and entry["date_of_joining"] == "2011-07-01"
    assert entry["name"] == "HARI DEMO"
    assert client.get(f"{MEMBER_BASE}/{option['option_id']}", headers=hdr(SUBJECTS["member-a"], "member")).status_code == 404


def test_member_who_joined_after_cutoff_is_not_eligible(ctx):
    client, q, _ = ctx
    response = client.post(MEMBER_BASE, json=option_body("2022-06"),
                           headers=hdr(SUBJECTS["member-a"], "member",
                                       {"action": "submit-higher-pension-option", "resource_id": "100000000001"}))
    assert response.status_code == 422, response.text
    assert response.json()["type"] == "/problems/not-eligible"
    assert "Only members in service" in response.json()["detail"]
    assert q("SELECT COUNT(*) FROM higher_pension_options") == [(0,)]


@pytest.mark.parametrize("higher_from,wages,expected_rows", [
    ("2014-09", WAGES, [("2014-09", 4000000, 1500000), ("2014-10", 4000000, 1500000), ("2015-01", 1200000, 1500000)]),
    ("2011-07", "2014-09,40000\n2011-07,40000\n2014-08,40000", [("2011-07", 4000000, 650000), ("2014-08", 4000000, 650000), ("2014-09", 4000000, 1500000)]),
    ("2014-09", "2014-09,15001\n2014-10,15002", [("2014-09", 1500100, 1500000), ("2014-10", 1500200, 1500000)]),
])
def test_dues_preview_uses_monthly_ceilings_and_integer_paise(ctx, higher_from, wages, expected_rows):
    client, q, _ = ctx
    option = submit(client, higher_from)
    response = client.post(f"{EMPLOYER_BASE}/{option['option_id']}/dues-previews", json=validation_body(wages), headers=employer())
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    expected_dues = [max(0, wage - ceiling) * 833 // 10000 for _, wage, ceiling in expected_rows]
    assert [(r["month"], r["wage_paise"], r["ceiling_paise"]) for r in data["wages"]] == expected_rows
    assert [r["dues_paise"] for r in data["wages"]] == expected_dues
    assert data["dues_paise"] == sum(expected_dues)
    assert "8.33%" in data["working"]
    assert q("SELECT state, dues_paise FROM higher_pension_options") == [("SUBMITTED", None)]
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='HigherPensionOptionValidated.v1'") == [(0,)]


@pytest.mark.parametrize("wages,message", [
    ("2014/09,40000", "write YYYY-MM"),
    ("2014-09,40000\n2014-09,41000", "given twice"),
    ("2014-08,40000", "before the month the member declared"),
])
@pytest.mark.parametrize("endpoint", ["dues-previews", "validations"])
def test_invalid_wage_lines_are_refused(ctx, wages, message, endpoint):
    client, q, _ = ctx
    option = submit(client)
    response = client.post(f"{EMPLOYER_BASE}/{option['option_id']}/{endpoint}", json=validation_body(wages), headers=employer())
    assert response.status_code == 422, response.text
    assert response.json()["type"] == "/problems/validation" and message in response.json()["detail"]
    assert q("SELECT state FROM higher_pension_options") == [("SUBMITTED",)]


def test_validation_is_bound_to_option_and_dues_and_emits_one_event(ctx):
    client, q, _ = ctx
    option = submit(client)
    option_id = option["option_id"]
    url = f"{EMPLOYER_BASE}/{option_id}/validations"
    body = validation_body()
    step = {"action": "validate-higher-pension", "resource_id": option_id, "amount_paise": DUES}
    assert client.post(url, json=body, headers=employer()).status_code == 428
    for wrong in ({"amount_paise": DUES + 1}, {"resource_id": "HPO-OTHER"}, {"action": "wrong-action"}):
        refused = client.post(url, json=body, headers=employer({**step, **wrong}))
        assert refused.status_code == 403 and refused.json()["type"] == "/problems/step-up-mismatch"
    assert q("SELECT state, dues_paise FROM higher_pension_options") == [("SUBMITTED", None)]
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='HigherPensionOptionValidated.v1'") == [(0,)]
    response = client.post(url, json=body, headers=employer(step))
    assert response.status_code == 200, response.text
    validated = response.json()["data"]
    assert validated["state"] == "VALIDATED" and validated["dues_paise"] == DUES == 416500
    assert validated["employer_note"] == body["note"] and len(validated["wages"]) == 3
    assert validated["validated_at"] and validated["rule_version"]
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='HigherPensionOptionValidated.v1'")
    event = json.loads(payload)["envelope"]["payload"]
    assert event == {"option_id": option_id, "uan": UAN, "account_link_id": "AL-0907", "establishment_id": EST,
                     "decision": "VALIDATED", "dues_paise": DUES, "months": 3, "rule_version": validated["rule_version"]}
    assert client.post(url, json=body, headers=employer(step)).status_code == 409
    assert q("SELECT COUNT(*) FROM outbox WHERE event_type='HigherPensionOptionValidated.v1'") == [(1,)]
    assert client.get(f"{MEMBER_BASE}/{option_id}", headers=hdr(MEMBER, "member")).json()["data"] == validated


def test_employer_rejects_with_a_note_without_wages(ctx):
    client, q, _ = ctx
    option = submit(client)
    option_id = option["option_id"]
    url = f"{EMPLOYER_BASE}/{option_id}/validations"
    body = {"decision": "REJECT", "note": "No payroll evidence of wages above the ceiling"}
    assert client.post(url, json=body, headers=employer()).status_code == 428
    step = {"action": "validate-higher-pension", "resource_id": option_id}
    response = client.post(url, json=body, headers=employer(step))
    assert response.status_code == 200, response.text
    rejected = response.json()["data"]
    assert rejected["state"] == "REJECTED_BY_EMPLOYER" and rejected["employer_note"] == body["note"]
    assert rejected["wages"] == [] and rejected["dues_paise"] is None
    [(payload,)] = q("SELECT payload FROM outbox WHERE event_type='HigherPensionOptionValidated.v1'")
    event = json.loads(payload)["envelope"]["payload"]
    assert event["decision"] == "REJECTED_BY_EMPLOYER" and event["dues_paise"] == event["months"] == 0
    assert client.post(url, json=body, headers=employer(step)).status_code == 409


def test_another_establishment_cannot_preview_or_validate(ctx):
    client, q, _ = ctx
    option = submit(client)
    option_id = option["option_id"]
    other = employer({"action": "validate-higher-pension", "resource_id": option_id, "amount_paise": DUES}, "EST-OTHER")
    assert client.get(EMPLOYER_BASE, headers=other).json()["data"] == []
    for endpoint in ("dues-previews", "validations"):
        response = client.post(f"{EMPLOYER_BASE}/{option_id}/{endpoint}", json=validation_body(), headers=other)
        assert response.status_code == 404, response.text
    assert q("SELECT state FROM higher_pension_options") == [("SUBMITTED",)]


def test_dues_preview_uses_a_published_rule_set(ctx):
    client, _, publish = ctx
    option = submit(client)
    publish(lambda document: document["higher_pension"].update(eps_share_bp=900), "higher-pension-test", "2020-01-01")
    response = client.post(f"{EMPLOYER_BASE}/{option['option_id']}/dues-previews", json=validation_body(), headers=employer())
    assert response.status_code == 200, response.text
    assert response.json()["data"]["dues_paise"] == 2 * (2500000 * 900 // 10000)
