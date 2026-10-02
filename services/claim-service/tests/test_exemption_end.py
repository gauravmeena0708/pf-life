"""The claim exemption projection follows the employer event without losing earlier trust service."""
import asyncio
from datetime import date

from app.domain.claims import eligibility
from epfo_persistence.policy import baseline
from tests.test_claims_api import ctx  # noqa: F401


def test_exemption_event_reseed_and_claim_dates(ctx):
    _, q, deliver = ctx
    from app.seed import main as seed
    est = "EST-DEMO-0005"
    payload = {"establishment_id": est, "status": "SURRENDERED", "ended_on": "2026-09-01",
               "past_accumulations_due": "2026-10-01"}
    deliver("ExemptionStatusChanged.v1", payload, "employer-service")
    deliver("ExemptionStatusChanged.v1", payload, "employer-service")
    asyncio.run(seed())
    assert q(f"SELECT status,ended_on FROM exempted_establishments WHERE establishment_id='{est}'") == [
        ("SURRENDERED", "2026-09-01")]
    assert q(f"SELECT COUNT(*) FROM exempted_establishments WHERE establishment_id='{est}'") == [(1,)]
    account = {"employee_paise": 4000000, "employer_paise": 2000000,
               "date_of_joining": date(2018, 6, 1), "date_of_exit": None,
               "exemption": {"pf_exempt": True, "status": "SURRENDERED", "ended_on": date(2026, 9, 1),
                             "effective_from": date(2008, 4, 1), "trust_name": "Demo Textile Trust"}}
    before = eligibility(account, "ADVANCE_ILLNESS", baseline(), date(2026, 8, 31))
    after = eligibility(account, "ADVANCE_ILLNESS", baseline(), date(2026, 9, 1))
    assert any("trust settles" in reason for reason in before["reasons"])
    assert not any("trust settles" in reason for reason in after["reasons"])
