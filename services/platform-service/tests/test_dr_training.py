"""Illustrative DR and training records use current rules, role checks and transactional events."""
import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert

from epfo_persistence.policy import baseline, policy_rules
from tests.test_interest_declaration import q
from tests.test_policy_admin import ctx, hdr  # noqa: F401 (fixture)

DR = "/api/v1/ndc/dr"
TRAINING = "/api/v1/training/sandboxes"
ADC = "tech.adc"
TRAINERS = ("train.pdnasa", "train.zti", "zo.zti")


def events(event_type):
    rows = q(f"SELECT payload FROM outbox WHERE event_type='{event_type}' ORDER BY id")
    return [(json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"])["envelope"]["payload"]
            for r in rows]


def publish_test_rules(**changes):
    from app.infra.db import sessions

    async def run():
        document = copy.deepcopy(baseline())
        document["dr_and_training"].update(changes)
        async with sessions()() as session, session.begin():
            await session.execute(insert(policy_rules).values(
                rule_version="dr-training-test", effective_from=datetime.now(UTC).date() - timedelta(days=1),
                document=document))
    asyncio.run(run())


def test_replication_status_is_repeatable_per_minute_and_flags_rpo(ctx):
    client, _ = ctx
    publish_test_rules(rpo_minutes=1)
    a = client.get(f"{DR}/replication-status", headers=hdr("adc-user", ADC))
    b = client.get(f"{DR}/replication-status", headers=hdr("adc-user", ADC))
    assert a.status_code == b.status_code == 200, a.text
    data = a.json()["data"]
    assert data == b.json()["data"]
    assert data["simulated"] is True and data["rpo_minutes"] == 1
    assert len(data["databases"]) == 14
    assert {r["database"] for r in data["databases"]} == {
        "employer", "member", "contribution", "claim", "workflow", "grievance", "audit", "reporting",
        "intelligence", "pension", "platform", "compliance", "international", "payment"}
    assert all(0 <= r["lag_seconds"] <= 1200 for r in data["databases"])
    assert all(r["status"] == ("LAGGING" if r["lag_seconds"] > 60 else "IN_SYNC") for r in data["databases"])
    assert data["overall_status"] == ("LAGGING" if any(r["status"] == "LAGGING" for r in data["databases"]) else "IN_SYNC")
    assert all(datetime.fromisoformat(r["last_applied_at"]).tzinfo is not None for r in data["databases"])
    assert q("SELECT * FROM outbox WHERE event_type <> 'PolicyPublished.v1'") == []   # the seed publishes the decided rule sets


@pytest.mark.parametrize("scenario", ["FULL_SITE", "DATABASE", "APPLICATION_TIER"])
def test_failover_drill_requires_bound_step_up_and_records_event(ctx, scenario):
    client, _ = ctx
    url = f"{DR}/failover-drills"
    body = {"scenario": scenario, "notes": "Planned illustrative exercise"}
    assert client.post(url, json=body, headers=hdr("adc-user", ADC)).status_code == 428
    assert client.post(url, json=body, headers=hdr("adc-user", ADC, {"action": "run-failover-drill",
                                                                    "resource_id": "OTHER"})).status_code == 403
    response = client.post(url, json=body, headers=hdr("adc-user", ADC, {"action": "run-failover-drill",
                                                                           "resource_id": scenario}))
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["simulated"] is True and data["within_target"] is True
    assert [s["step"] for s in data["steps"]] == ["freeze writes", "promote replica", "switch DNS", "smoke test"]
    assert sum(s["duration_minutes"] for s in data["steps"]) == data["rto_minutes"]
    assert data["rto_minutes"] <= data["target_minutes"] == 120
    [record] = q("SELECT * FROM failover_drills")
    assert record["drill_id"] == data["drill_id"]
    assert events("FailoverDrillRecorded.v1") == [{"drill_id": data["drill_id"], "scenario": scenario,
                                                    "rto_minutes": data["rto_minutes"], "within_target": True}]


def test_small_rto_marks_drill_outside_target(ctx):
    client, _ = ctx
    publish_test_rules(rto_minutes=1)
    response = client.post(f"{DR}/failover-drills", json={"scenario": "DATABASE"},
                           headers=hdr("adc-user", ADC, {"action": "run-failover-drill", "resource_id": "DATABASE"}))
    assert response.status_code == 201, response.text
    assert response.json()["data"]["target_minutes"] == 1
    assert response.json()["data"]["within_target"] is False
    assert events("FailoverDrillRecorded.v1")[0]["within_target"] is False


@pytest.mark.parametrize("role", TRAINERS)
def test_training_sandbox_records_synthetic_logins_and_event(ctx, role):
    client, _ = ctx
    body = {"course": "Claims handling", "trainees": 3, "personas": ["member-a", "ro-ss"],
            "starts_on": "2026-10-02"}
    response = client.post(TRAINING, json=body, headers=hdr("trainer", role))
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["expires_on"] == "2026-10-16" and data["simulated"] is True
    assert "Synthetic data only" in data["note"]
    assert [r["persona"] for r in data["training_logins"]] == ["member-a", "ro-ss", "member-a"]
    assert [r["username"] for r in data["training_logins"]] == [
        f"trainee-{data['sandbox_id'][4:].lower()}-{i}" for i in (1, 2, 3)]
    [record] = q("SELECT * FROM training_sandboxes")
    assert record["sandbox_id"] == data["sandbox_id"]
    assert events("TrainingSandboxCreated.v1") == [{"sandbox_id": data["sandbox_id"], "course": body["course"],
                                                     "trainees": 3, "expires_on": "2026-10-16"}]


def test_training_uses_sandbox_days_rule(ctx):
    client, _ = ctx
    publish_test_rules(sandbox_days=2)
    response = client.post(TRAINING, json={"course": "DR training", "trainees": 1,
                                                 "personas": ["emp-owner"], "starts_on": datetime.now(UTC).date().isoformat()},
                           headers=hdr("trainer", "train.zti"))
    assert response.status_code == 201, response.text
    assert response.json()["data"]["expires_on"] == (datetime.now(UTC).date() + timedelta(days=2)).isoformat()


def test_invalid_input_and_other_roles_create_no_records(ctx):
    client, _ = ctx
    drill = f"{DR}/failover-drills"
    adc = hdr("adc-user", ADC, {"action": "run-failover-drill", "resource_id": "OTHER"})
    assert client.post(drill, json={"scenario": "OTHER"}, headers=adc).status_code == 422
    body = {"course": "Claims handling", "trainees": 1, "personas": ["member-a"], "starts_on": "2026-10-02"}
    trainer = hdr("trainer", "train.zti")
    for change in ({"trainees": 61}, {"trainees": 0}, {"personas": ["real-user"]}, {"personas": []}):
        assert client.post(TRAINING, json={**body, **change}, headers=trainer).status_code == 422
    assert client.post(TRAINING, json={**body, "course": "x"}, headers=trainer).status_code == 400
    member = hdr("member", "member")
    assert client.get(f"{DR}/replication-status", headers=member).status_code == 403
    assert client.post(drill, json={"scenario": "DATABASE"}, headers=member).status_code == 403
    assert client.post(TRAINING, json=body, headers=member).status_code == 403
    assert q("SELECT * FROM failover_drills") == []
    assert q("SELECT * FROM training_sandboxes") == []
    assert q("SELECT * FROM outbox WHERE event_type <> 'PolicyPublished.v1'") == []   # the seed publishes the decided rule sets
