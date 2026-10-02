"""Interest declaration events create one valid draft from the in-force policy."""
import asyncio
import copy
import json
import uuid
from datetime import date

from sqlalchemy import insert, text

from epfo_persistence.consumer import apply_once
from epfo_persistence.policy import validate
from tests.test_policy_admin import baseline_doc, ctx


def q(sql):
    from app.infra.db import engine

    async def read():
        async with engine().connect() as connection:
            return (await connection.execute(text(sql))).mappings().all()
    return asyncio.run(read())


def deliver(event):
    from app.infra.db import sessions
    from app.infra.messaging import dispatch
    return asyncio.run(apply_once(sessions(), event, dispatch))


def test_interest_declaration_drafts_valid_policy_once_from_in_force_version(ctx, monkeypatch):
    client, _ = ctx
    from app.infra import messaging
    monkeypatch.setattr(messaging, "today", lambda: date(2026, 9, 30))
    base_doc = baseline_doc(client)
    # A newer published policy is in force, and a still newer publication is future-dated.
    # The consumer must inherit the former's changes without selecting the latter.
    from app.infra.db import sessions
    from app.infra.tables import rule_sets

    async def publications():
        async with sessions()() as session, session.begin():
            for vid, effective, ceiling in (("POL-IN-FORCE", date(2026, 9, 20), 2500000),   # after the seeded ₹25,000 version of 17 Sep
                                             ("POL-FUTURE", date(2026, 10, 1), 3000000)):
                doc = copy.deepcopy(base_doc)
                doc["rule_version"] = vid
                doc["effective_from"] = effective.isoformat()
                doc["contribution"]["eps_wage_ceiling_paise"] = ceiling
                await session.execute(insert(rule_sets).values(
                    version_id=vid, rule_version=vid, effective_from=effective,
                    status="PUBLISHED", document=doc, base_version_id="POL-BASELINE",
                    drafted_by="seed", change_note="Published test ceiling", version=1))
    asyncio.run(publications())
    payload = {"declaration_id": "IRD-TEST0001", "financial_year": "2025-26", "rate_bp": 850,
               "cbt_recommended_on": "2026-03-01", "ministry_concurrence_ref": "DEMO/MINISTRY/01",
               "ministry_concurrence_on": "2026-03-15"}
    event = {"event_id": str(uuid.uuid4()), "event_type": "InterestRateDeclared.v1",
             "producer": "contribution-service", "correlation_id": str(uuid.uuid4()), "payload": payload}
    before = q("SELECT version_id, document FROM rule_sets WHERE status='PUBLISHED' ORDER BY version_id")
    assert deliver(event) is True
    [draft] = q("SELECT * FROM rule_sets WHERE status='DRAFT'")
    document = json.loads(draft["document"]) if isinstance(draft["document"], str) else draft["document"]
    assert draft["base_version_id"] == "POL-IN-FORCE"
    assert draft["drafted_by"].startswith("SYSTEM:") and payload["declaration_id"] in draft["drafted_by"]
    assert document["interest"]["rates_bp"]["2025-26"] == 850
    assert document["contribution"]["eps_wage_ceiling_paise"] == 2500000
    assert validate(document) == []
    assert deliver(event) is False  # inbox deduplicates an actual redelivery
    assert deliver({**event, "event_id": str(uuid.uuid4())}) is True  # declaration deduplicates a fresh envelope
    assert q("SELECT * FROM rule_sets WHERE status='DRAFT'") == [draft]
    assert q("SELECT version_id, document FROM rule_sets WHERE status='PUBLISHED' ORDER BY version_id") == before
