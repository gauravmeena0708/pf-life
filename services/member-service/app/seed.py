"""Load deterministic synthetic members and employments. Idempotent: python -m app.seed"""
import asyncio
import json
import os
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db import sessions
from app.infra.tables import contact_history, employments, members

SEED_FILE = os.environ.get("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as file:
        seed = json.load(file)
    establishment = seed["establishment"]
    async with sessions()() as session:
        insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
        async with session.begin():
            for member in seed["members"]:
                values = {"member_id": member["member_id"], "uan": member["uan"],
                          "subject": member["subject"], "name": member["name"],
                          "date_of_birth": date.fromisoformat(member["date_of_birth"]),
                          "gender": member["gender"], "mobile_masked": member["mobile_masked"],
                          "email_masked": member["email_masked"], "bank_ifsc": member["bank_ifsc"],
                          "bank_account_last4": member["bank_account_last4"], "kyc": member["kyc"]}
                statement = insert(members).values(**values)
                await session.execute(statement.on_conflict_do_update(
                    index_elements=[members.c.member_id],
                    # contact details belong to the member after the first load; a re-seed must not undo a change
                    set_={key: statement.excluded[key] for key in values
                          if key not in ("member_id", "mobile_masked", "email_masked")}))
                has_history = (await session.execute(select(contact_history.c.id).where(
                    contact_history.c.member_id == member["member_id"]).limit(1))).first()
                if not has_history:
                    await session.execute(contact_history.insert().values(
                        member_id=member["member_id"], mobile_masked=member["mobile_masked"],
                        email_masked=member["email_masked"], source="SEED", verified=True))
                names = {e["establishment_id"]: e["legal_name"] for e in [establishment, *seed.get("public_establishments", [])]}
                for job in [{**member, "establishment_id": establishment["establishment_id"]}, *member.get("previous_employments", [])]:
                    employment = {"account_link_id": job["account_link_id"], "member_id": member["member_id"],
                                  "establishment_id": job["establishment_id"], "establishment_name": names[job["establishment_id"]],
                                  "date_of_joining": date.fromisoformat(job["date_of_joining"]),
                                  "date_of_exit": date.fromisoformat(job["date_of_exit"]) if job.get("date_of_exit") else None,
                                  "exit_marked_by": "SEED" if job.get("date_of_exit") else None,
                                  "last_contribution_month": job.get("last_contribution_month")}
                    statement = insert(employments).values(**employment)
                    # Exits, contributions and transfers move after the first load; a re-seed keeps them.
                    await session.execute(statement.on_conflict_do_update(
                        index_elements=[employments.c.account_link_id],
                        set_={key: statement.excluded[key] for key in ("member_id", "establishment_id", "establishment_name", "date_of_joining")}))
    print(f"member-service seeded: {len(seed['members'])} synthetic members")


if __name__ == "__main__":
    asyncio.run(main())
