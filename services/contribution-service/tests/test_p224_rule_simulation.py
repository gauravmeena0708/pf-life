"""P2.24: a proposed rule is evaluated against synthetic member accounts without posting it."""
from tests.test_ecr_api import SEED, approved, ctx, hdr, signatory  # noqa: F401

URL = "/api/v1/office/accounts/rule-change-simulations"
FINANCE = SEED["keycloak_subjects"]["ho-finance"]


def submitted_return(client):
    """A real return (the ECR tests' good file) approved and submitted, so the members have wages to simulate on."""
    f, total = approved(client)
    step = {"action": "submit-ecr", "resource_id": f["filing_id"], "resource_version": f["version"], "amount_paise": total}
    assert client.post(f"/api/v1/employers/me/ecr-filings/{f['filing_id']}/submissions",
                       headers=signatory(step, **{"Idempotency-Key": "sim", "If-Match": str(f["version"])})).status_code == 201


def office():
    return hdr(FINANCE, "ho.fa_cao", [], establishment=None)


def test_current_rules_have_no_effect_and_only_audit_is_saved(ctx):
    client, q = ctx
    before = {table: q(f"SELECT COUNT(*) FROM {table}")[0][0] for table in
              ("journals", "journal_lines", "interest_postings", "demo_calculations", "outbox", "audit_local")}
    response = client.post(URL, json={"financial_year": "2025-26", "interest_rate_bp": 825}, headers=office())
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["sample_size"] > 0 and data["total_change_paise"] == 0
    assert all(b["min_change_paise"] == b["median_change_paise"] == b["max_change_paise"] == 0 for b in data["bands"])
    assert len(data["illustrative_members"]) == 3
    assert all(m["synthetic_id"].startswith("SIM-") and m["change_paise"] == 0 for m in data["illustrative_members"])
    after = {table: q(f"SELECT COUNT(*) FROM {table}")[0][0] for table in before}
    assert {k: after[k] - before[k] for k in before} == {**{k: 0 for k in before}, "audit_local": 1}
    assert q("SELECT actor_subject, action FROM audit_local WHERE action='rule_change.simulated'") == [(FINANCE, "rule_change.simulated")]


def test_higher_interest_rate_raises_every_account_with_interest(ctx):
    client, _ = ctx
    response = client.post(URL, json={"financial_year": "2025-26", "interest_rate_bp": 850}, headers=office())
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["total_change_paise"] > 0
    assert sum(b["gain_count"] for b in data["bands"]) > 0                  # every account earning interest gains
    assert sum(b["lose_count"] for b in data["bands"]) == 0                 # and nobody loses (no balance: no change)


def test_office_only_and_split_or_ceiling_change_uses_same_sample(ctx):
    client, _ = ctx
    assert client.post(URL, json={"financial_year": "2025-26", "interest_rate_bp": 850},
                       headers=hdr("member", "member", [], establishment=None)).status_code == 403
    submitted_return(client)
    raised = client.post(URL, json={"financial_year": "2025-26", "employee_rate_bp": 1300}, headers=office())
    assert raised.status_code == 200, raised.json()
    data = raised.json()["data"]
    assert data["total_change_paise"] > 0           # 13% from the employee (the employer's follows): more PF credit
    assert data["sample_size"] == sum(b["member_count"] for b in data["bands"])
    shifted = client.post(URL, json={"financial_year": "2025-26", "employee_rate_bp": 1300, "employer_rate_bp": 1100},
                          headers=office()).json()["data"]
    assert shifted["total_change_paise"] == 0       # 13% + 11% is today's 24%: the PF credit does not move
    ceiling = client.post(URL, json={"financial_year": "2025-26", "wage_ceiling_paise": 3000000}, headers=office()).json()["data"]
    assert ceiling["total_change_paise"] <= 0       # a higher pension ceiling moves employer money from PF to EPS
