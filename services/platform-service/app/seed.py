"""Idempotently record the baseline rule set (config/demo-rules.yaml) as the first published version."""
import asyncio
from datetime import date

from sqlalchemy import select

from app.infra.db import sessions
from app.infra.tables import rule_sets
from epfo_persistence.policy import baseline

BASELINE_ID = "POL-BASELINE"


async def main() -> None:
    doc = baseline()
    async with sessions()() as session, session.begin():
        if not (await session.execute(select(rule_sets.c.version_id).where(rule_sets.c.version_id == BASELINE_ID))).first():
            await session.execute(rule_sets.insert().values(
                version_id=BASELINE_ID, rule_version=doc["rule_version"], effective_from=date.fromisoformat(doc["effective_from"]),
                status="PUBLISHED", document=doc, base_version_id=None, drafted_by="seed", decided_by="seed",
                change_note="Baseline rule set from config/demo-rules.yaml", version=1))
    print(f"platform-service seeded: baseline rule set {doc['rule_version']}")


if __name__ == "__main__":
    asyncio.run(main())
