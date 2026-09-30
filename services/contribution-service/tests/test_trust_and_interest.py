"""Interest declarations and atomic, balanced surrendered-trust ingestion."""
import pytest

from tests.test_ecr_api import SEED, ctx
from tests.test_ledger_work import events
from tests.test_returns import office

S = SEED["keycloak_subjects"]
EST = "EST-DEMO-0003"
FY = "2025-26"
RATE = {"rate_bp": 850, "cbt_recommended_on": "2026-03-01",
        "ministry_concurrence_ref": "DEMO/MINISTRY/01", "ministry_concurrence_on": "2026-03-15"}
CSV = ("uan,account_link_id,employee_rupees,employer_rupees,pension_rupees\n"
       "100000000908,AL-0910,1000,500,200\n"
       "100000000909,AL-0912,2000,1000,0\n")
TOTAL = 470000


def record_rate(client, year=FY, body=None, **step_changes):
    step = {"action": "record-interest-rate", "resource_id": year,
            "amount_paise": RATE["rate_bp"], **step_changes}
    return client.put(f"/api/v1/ho/config/interest-rates/{year}", json=body or RATE,
                      headers=office(S["ho-finance"], "ho.fa_cao", step))


def ingest(client, *, establishment=EST, content=CSV, reference="TRUST-TRANSFER-TEST", **step_changes):
    step = {"action": "ingest-past-accumulation", "resource_id": establishment,
            "amount_paise": TOTAL, **step_changes}
    return client.post(f"/api/v1/office/exempted/{establishment}/past-accumulation-ingestions",
                       json={"transfer_reference": reference, "content": content},
                       headers=office(S["ro-exemption"], "fo.exemption", step))


def snapshot(q):
    return {table: q(f"SELECT * FROM {table} ORDER BY 1")
            for table in ("journals", "journal_lines", "past_accumulation_ingestions", "outbox")}


def test_interest_declaration_records_bound_rate_and_emits_event(ctx):
    client, q = ctx
    response = record_rate(client)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["financial_year"] == FY and data["rate_bp"] == 850
    [event] = events(q, "InterestRateDeclared.v1")
    assert event == {"declaration_id": data["declaration_id"], "financial_year": FY, **RATE}
    assert q("SELECT financial_year, rate_bp, recorded_by FROM interest_rate_declarations") == [
        (FY, 850, S["ho-finance"]),
    ]


@pytest.mark.parametrize("year, body", [
    ("2025-27", RATE),
    (FY, {**RATE, "ministry_concurrence_on": "2026-02-28"}),
])
def test_invalid_year_or_concurrence_before_recommendation_is_not_recorded(ctx, year, body):
    client, q = ctx
    response = record_rate(client, year, body)
    assert response.status_code == 422, response.text
    assert q("SELECT declaration_id FROM interest_rate_declarations") == []
    assert events(q, "InterestRateDeclared.v1") == []


@pytest.mark.parametrize("step_changes", [
    {"amount_paise": 849}, {"resource_id": "2024-25"}, {"action": "ingest-past-accumulation"},
])
def test_interest_step_up_must_match_action_year_and_rate(ctx, step_changes):
    client, q = ctx
    response = record_rate(client, **step_changes)
    assert response.status_code == 403, response.text
    assert q("SELECT declaration_id FROM interest_rate_declarations") == []
    assert events(q, "InterestRateDeclared.v1") == []


def test_past_accumulation_posts_one_balanced_journal_and_ledger_event_per_member(ctx):
    client, q = ctx
    response = ingest(client)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["establishment_id"] == EST and data["members"] == 2 and data["total_paise"] == TOTAL
    assert [(line["uan"], line["account_link_id"]) for line in data["lines"]] == [
        ("100000000908", "AL-0910"), ("100000000909", "AL-0912"),
    ]
    ids = [line["journal_id"] for line in data["lines"]]
    assert len(set(ids)) == 2 and all(ids)
    ledger_events = events(q, "LedgerAdjusted.v1")
    assert len(ledger_events) == 2
    by_journal = {event["journal_id"]: event for event in ledger_events}
    for line, expected_total in zip(data["lines"], (170000, 300000)):
        journal_id = line["journal_id"]
        assert q(f"SELECT kind FROM journals WHERE id='{journal_id}'") == [("PAST_ACCUMULATION",)]
        postings = q(f"SELECT account_code, side, amount_paise, account_link_id, share "
                     f"FROM journal_lines WHERE journal_id='{journal_id}' ORDER BY id")
        assert sum(p[2] for p in postings if p[1] == "debit") == expected_total
        assert sum(p[2] for p in postings if p[1] == "credit") == expected_total
        assert ("TRUST_TRANSFER_RECEIVABLE", "debit", expected_total, None, None) in postings
        assert ("AC01_EPF", "credit", line["employee_paise"], line["account_link_id"], "employee") in postings
        assert ("AC01_EPF", "credit", line["employer_paise"], line["account_link_id"], "employer") in postings
        if line["pension_paise"]:
            assert ("AC10_EPS", "credit", line["pension_paise"], None, None) in postings
        event = by_journal[journal_id]
        assert event["appendix_type"] == "PAST_ACCUMULATION" and event["account_link_id"] == line["account_link_id"]
        assert [(p["account_code"], p["side"], p["amount_paise"], p.get("account_link_id"), p.get("share"))
                for p in event["postings"]] == [tuple(p) for p in postings]
    [event] = events(q, "TrustAccumulationIngested.v1")
    assert event == {"batch_id": data["batch_id"], "establishment_id": EST,
                     "transfer_reference": "TRUST-TRANSFER-TEST", "members": 2, "total_paise": TOTAL}


@pytest.mark.parametrize("step_changes", [
    {"amount_paise": TOTAL - 1}, {"resource_id": "EST-DEMO-0001"}, {"action": "record-interest-rate"},
])
def test_ingestion_rejects_wrong_step_up_without_posting(ctx, step_changes):
    client, q = ctx
    before = snapshot(q)
    response = ingest(client, **step_changes)
    assert response.status_code == 403, response.text
    assert snapshot(q) == before


def test_another_establishments_member_rejects_entire_batch(ctx):
    client, q = ctx
    before = snapshot(q)
    content = CSV + "100000000001,AL-0001,100,50,0\n"
    response = ingest(client, content=content, amount_paise=TOTAL + 15000)
    assert response.status_code == 422, response.text
    assert snapshot(q) == before


def test_transfer_reference_cannot_be_ingested_twice(ctx):
    client, q = ctx
    response = ingest(client)
    assert response.status_code == 201, response.text
    before = snapshot(q)
    response = ingest(client)
    assert response.status_code == 409, response.text
    assert snapshot(q) == before


def test_non_surrendered_establishment_cannot_ingest(ctx):
    client, q = ctx
    before = snapshot(q)
    response = ingest(client, establishment="EST-DEMO-0001")
    assert response.status_code == 409, response.text
    assert snapshot(q) == before
