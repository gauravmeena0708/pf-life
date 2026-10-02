"""Idempotently record the baseline rule set (config/demo-rules.yaml) as the first published version, then the versions
already decided after it (its `revisions:`), each published as an approval would: stored, and announced to every service
with PolicyPublished.v1."""
import asyncio
import uuid
from datetime import date

from sqlalchemy import insert, select

from app.api.routes import sha256
from app.infra.db import sessions
from app.infra.tables import rule_sets
from epfo_persistence import add_event
from epfo_persistence.policy import baseline, policy_rules, revisions

BASELINE_ID = "POL-BASELINE"


async def main() -> None:
    doc = baseline()
    async with sessions()() as session, session.begin():
        if not (await session.execute(select(rule_sets.c.version_id).where(rule_sets.c.version_id == BASELINE_ID))).first():
            await session.execute(rule_sets.insert().values(
                version_id=BASELINE_ID, rule_version=doc["rule_version"], effective_from=date.fromisoformat(doc["effective_from"]),
                status="PUBLISHED", document=doc, base_version_id=None, drafted_by="seed", decided_by="seed",
                change_note="Baseline rule set from config/demo-rules.yaml", version=1))
        base_id = BASELINE_ID
        for revision in revisions():
            r = revision["document"]
            version_id = f"POL-{r['rule_version']}"
            if not (await session.execute(select(rule_sets.c.version_id).where(rule_sets.c.version_id == version_id))).first():
                effective = date.fromisoformat(r["effective_from"])
                await session.execute(rule_sets.insert().values(
                    version_id=version_id, rule_version=r["rule_version"], effective_from=effective, status="PUBLISHED",
                    document=r, base_version_id=base_id, drafted_by="seed", decided_by="seed",
                    change_note=revision["change_note"], version=1))
                if not (await session.execute(select(policy_rules.c.rule_version).where(policy_rules.c.rule_version == r["rule_version"]))).first():
                    await session.execute(insert(policy_rules).values(rule_version=r["rule_version"], effective_from=effective, document=r))
                await add_event(session, producer="platform-service", event_type="PolicyPublished.v1", aggregate_type="rule_set",
                                aggregate_id=version_id, correlation_id=str(uuid.uuid4()), payload={
                                    "version_id": version_id, "rule_version": r["rule_version"], "effective_from": r["effective_from"],
                                    "document_sha256": sha256(r), "approved_by_role": "ho.policy", "document": r})
                print(f"platform-service seeded: rule set {r['rule_version']} from {r['effective_from']}")
            base_id = version_id
    print(f"platform-service seeded: baseline rule set {doc['rule_version']}")


if __name__ == "__main__":
    asyncio.run(main())
