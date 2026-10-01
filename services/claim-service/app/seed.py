"""Idempotently load the synthetic account projection (with opening balances) and office postings."""
import asyncio
import json
import os
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.infra.db import sessions
from app.infra.tables import accounts, exempted_establishments, member_bank_accounts, nominations, office_staff

SEED_FILE = os.getenv("SEED_FILE", "/srv/seed/synthetic.json")


def _identity(m: dict) -> dict:
    """Date of birth and, for an international worker, the nationality (P2.9a)."""
    intl = m.get("international") or {}
    return {"date_of_birth": date.fromisoformat(m["date_of_birth"]), "international_worker": bool(intl),
            "nationality": intl.get("nationality")}


async def main() -> None:
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    office_id = seed["establishment"]["office_id"]
    opening = {k: v for k, v in seed.get("opening_balances", {}).items() if not k.startswith("_")}
    async with sessions()() as session, session.begin():
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        jobs = [{"establishment_id": seed["establishment"]["establishment_id"], **m} for m in seed["members"]]
        jobs += [{**m, **job} for m in seed["members"] for job in m.get("previous_employments", [])]   # earlier member IDs
        for m in jobs:
            balance = opening.get(m["account_link_id"], {})
            exists = (await session.execute(select(accounts.c.account_link_id).where(
                accounts.c.account_link_id == m["account_link_id"]))).first()
            if exists:   # balances move with events after the first load; only refresh identity fields
                await session.execute(update(accounts).where(accounts.c.account_link_id == m["account_link_id"])
                                      .values(member_subject=m.get("subject"), member_name=m.get("name"), office_id=office_id, uan=m["uan"],
                                              establishment_id=m["establishment_id"],
                                              pan_verified=m["kyc"]["pan"] == "VERIFIED", aadhaar_verified=m["kyc"]["aadhaar"] == "VERIFIED",
                                              **_identity(m)))    # exits move with MemberExitMarked.v1
                continue
            await session.execute(insert(accounts).values(
                account_link_id=m["account_link_id"], member_subject=m.get("subject"), member_name=m.get("name"), uan=m["uan"],
                establishment_id=m["establishment_id"], office_id=office_id,
                date_of_joining=date.fromisoformat(m["date_of_joining"]),
                date_of_exit=date.fromisoformat(m["date_of_exit"]) if m.get("date_of_exit") else None,
                employee_paise=balance.get("employee_paise", 0), employer_paise=balance.get("employer_paise", 0),
                pan_verified=m["kyc"]["pan"] == "VERIFIED", aadhaar_verified=m["kyc"]["aadhaar"] == "VERIFIED",
                deceased_on=date.fromisoformat(m["deceased_on"]) if m.get("deceased_on") else None, **_identity(m)))
        # P2.7d: the primary member ID of each member's Aadhaar-verified set (the same rule member-service applies)
        from epfo_persistence.member_ids import primary_member_id
        sets: dict[str, list[dict]] = {}
        for m in seed["members"]:
            key = m.get("aadhaar_ref") if m["kyc"]["aadhaar"] == "VERIFIED" and m.get("aadhaar_ref") else m["uan"]
            sets.setdefault(key, []).append(m)
        for group in sets.values():
            ids = [{"account_link_id": j["account_link_id"], "date_of_joining": j["date_of_joining"],
                    "last_contribution_month": j.get("last_contribution_month"), "transferred_to": None}
                   for m in group for j in [m, *m.get("previous_employments", [])]]
            primary, key = primary_member_id(ids), ",".join(sorted(m["uan"] for m in group))
            for i in ids:
                await session.execute(update(accounts).where(accounts.c.account_link_id == i["account_link_id"],
                                                             accounts.c.set_key.is_(None)).values(is_primary=i["account_link_id"] == primary, set_key=key))
        for m in seed["members"]:                                 # nominations on record (e-nomination is planned)
            for i, n in enumerate(m.get("nominations", []), start=1):
                await session.execute(insert(nominations).values(
                    nomination_id=f"NOM-{m['uan']}-{i}", uan=m["uan"], name=n["name"], relation=n["relation"], share_bp=n["share_bp"],
                    subject=n.get("subject"), bank_ifsc=n.get("bank_ifsc"), bank_account_last4=n.get("bank_account_last4")).on_conflict_do_nothing())
        for m in seed["members"]:                                 # KYC-verified bank accounts (P2.8b)
            banks = [{"bank_ifsc": m["bank_ifsc"], "bank_account_last4": m["bank_account_last4"]}] if m["kyc"]["bank"] == "VERIFIED" else []
            for b in banks + m.get("other_bank_accounts", []):
                await session.execute(insert(member_bank_accounts).values(uan=m["uan"], bank_ifsc=b["bank_ifsc"],
                                                                          bank_account_last4=b["bank_account_last4"]).on_conflict_do_nothing())
        for s in seed.get("office_staff", []):
            await session.execute(insert(office_staff).values(subject=s["subject"], stakeholder=s["stakeholder"],
                                                              office_id=s["office_id"]).on_conflict_do_nothing())
        if e := seed.get("exempted_establishment"):
            values = {k: e[k] for k in ("establishment_id", "kind", "pf_exempt", "pension_exempt", "edli_exempt",
                                        "notification_no", "status", "trust_id", "trust_name", "trust_users")}
            values.update(notification_date=date.fromisoformat(e["notification_date"]),
                          effective_from=date.fromisoformat(e["effective_from"]))
            await session.execute(insert(exempted_establishments).values(**values).on_conflict_do_update(
                index_elements=["establishment_id"], set_=values))
    print(f"claim-service seeded: {len(seed['members'])} accounts, {len(seed.get('office_staff', []))} office staff")


if __name__ == "__main__":
    asyncio.run(main())
