"""P2.27: every event written to the outbox is checked against its contract wherever the contracts are found."""
import pytest

from epfo_persistence.contracts import ContractViolation, check
from epfo_persistence.events import envelope


def event(event_type="ChallanGenerated.v1", **payload):
    body = {"trrn": "TRRN0000000000001", "establishment_id": "EST-DEMO-0001", "kind": "DIRECT_ADMIN", "total_paise": 50000,
            "reference_id": "TRRN0000000000001", **payload}
    return envelope(producer="contribution-service", event_type=event_type, aggregate_type="challan", aggregate_id="TRRN0000000000001",
                    payload=body, correlation_id="5b1f7c62-6d5e-4a52-9f0c-9d5b1c3b2a10")


def test_a_matching_event_passes():
    check(event())


def test_a_drifted_payload_names_every_difference():
    with pytest.raises(ContractViolation) as e:
        check(event(kind="SOMETHING_ELSE", unexpected="x"))
    assert "payload/kind" in str(e.value) and "unexpected" in str(e.value)


def test_an_event_without_a_contract_is_refused():
    with pytest.raises(ContractViolation, match="has no contract"):
        check(event("NeverDefined.v1"))
