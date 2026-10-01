"""Idempotently load the synthetic office and office postings."""
import asyncio
import json
import os

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from datetime import date, datetime

from app.infra.tables import ledger_locks, member_accounts, office_staff, offices, outreach_camps, subject_offices

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    office = seed["office"]
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        for o in [office, *seed.get("other_offices", [])]:
            await session.execute(insert(offices).values(office_id=o["office_id"], name=o["name"],
                                                         zone_id=o.get("zone_id")).on_conflict_do_nothing())
        for camp in seed.get("outreach_camps", []):
            await session.execute(insert(outreach_camps).values(
                camp_id=camp["camp_id"], office_id=camp["office_id"],
                held_on=date.fromisoformat(camp["held_on"]), venue=camp["venue"]
            ).on_conflict_do_nothing())
        for m in seed["members"]:               # process subjects (UANs) belong to the establishment's office
            values = {"office_id": seed["establishment"]["office_id"], "zone_id": office.get("zone_id"),
                      "member_subject": m.get("subject"), "establishment_id": seed["establishment"]["establishment_id"]}
            statement = insert(subject_offices).values(subject_ref=m["uan"], **values)
            await session.execute(statement.on_conflict_do_update(index_elements=[subject_offices.c.subject_ref], set_=values))
            # Member accounts: the current one and any earlier member IDs. Exits and transfers move them after
            # the first load (events), so a re-seed does not overwrite them.
            for a in [{**m, "establishment_id": seed["establishment"]["establishment_id"]}, *m.get("previous_employments", [])]:
                await session.execute(insert(member_accounts).values(
                    account_link_id=a["account_link_id"], uan=m["uan"], member_subject=m.get("subject"), establishment_id=a["establishment_id"],
                    date_of_joining=date.fromisoformat(a["date_of_joining"]),
                    date_of_exit=date.fromisoformat(a["date_of_exit"]) if a.get("date_of_exit") else None).on_conflict_do_nothing())
        est = seed["establishment"]              # the establishment is a process subject too (establishment freeze)
        values = {"office_id": est["office_id"], "zone_id": office.get("zone_id"), "member_subject": None, "establishment_id": est["establishment_id"]}
        await session.execute(insert(subject_offices).values(subject_ref=est["establishment_id"], **values)
                              .on_conflict_do_update(index_elements=[subject_offices.c.subject_ref], set_=values))
        for lock in seed.get("ledger_locks", []):   # a lock left behind by a process that died (orphaned)
            await session.execute(insert(ledger_locks).values(
                **{k: v for k, v in lock.items() if not k.startswith("_") and k not in ("acquired_at", "expires_at")},
                office_id=est["office_id"], acquired_at=datetime.fromisoformat(lock["acquired_at"]),
                expires_at=datetime.fromisoformat(lock["expires_at"])).on_conflict_do_nothing())
        # P2.7d: the primary member ID of each member's Aadhaar-verified set (the same rule member-service applies)
        from epfo_persistence.member_ids import primary_member_id
        groups: dict[str, list[dict]] = {}
        for m in seed["members"]:
            key = m.get("aadhaar_ref") if m["kyc"]["aadhaar"] == "VERIFIED" and m.get("aadhaar_ref") else m["uan"]
            groups.setdefault(key, []).append(m)
        for group in groups.values():
            ids = [{"account_link_id": j["account_link_id"], "date_of_joining": j["date_of_joining"],
                    "last_contribution_month": j.get("last_contribution_month"), "transferred_to": None}
                   for m in group for j in [m, *m.get("previous_employments", [])]]
            primary = primary_member_id(ids)
            has_primary = (await session.execute(select(member_accounts.c.account_link_id).where(
                member_accounts.c.account_link_id.in_([i["account_link_id"] for i in ids]), member_accounts.c.is_primary))).first()
            if not has_primary:                                     # later changes arrive by event; a re-seed keeps them
                for i in ids:
                    await session.execute(update(member_accounts).where(member_accounts.c.account_link_id == i["account_link_id"])
                                          .values(is_primary=i["account_link_id"] == primary))
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(
                subject=s["subject"], username=s["username"], stakeholder=s["stakeholder"],
                office_id=s["office_id"]).on_conflict_do_nothing())
            await session.execute(update(office_staff).where(office_staff.c.subject == s["subject"], office_staff.c.posted_since.is_(None))
                                  .values(posted_since=date.fromisoformat(s.get("posted_since", "2025-04-01"))))   # P2.10b: tenure
    print(f"workflow-service seeded: office {office['office_id']}, {len(seed.get('office_staff', []))} postings")


if __name__ == "__main__":
    asyncio.run(main())
