"""Load deterministic synthetic seed data (scripts/seed/synthetic.json). Idempotent: python -m app.seed"""
import asyncio
import json
import os
from datetime import date, datetime

from sqlalchemy import select, update

from app.infra.db import sessions
from app.infra.tables import directory, establishments, grants, office_staff, registration_requests

SEED_FILE = os.environ.get("SEED_FILE", "/srv/seed/synthetic.json")
PUBLIC_FIELDS = ("pincode", "city", "district", "coverage_date", "establishment_type",
                 "industry_group", "exemption_status")


def public_fields(record: dict) -> dict:
    fields = {name: record.get(name) for name in PUBLIC_FIELDS}
    if fields["coverage_date"]:
        fields["coverage_date"] = date.fromisoformat(fields["coverage_date"])
    return fields


async def main() -> None:
    seed = json.load(open(SEED_FILE, encoding="utf-8"))
    est = seed["establishment"]
    async with sessions()() as s:
        async with s.begin():
            if not (await s.execute(select(establishments.c.establishment_id).where(
                    establishments.c.establishment_id == est["establishment_id"]))).first():
                await s.execute(establishments.insert().values(
                    establishment_id=est["establishment_id"], registration_number=est["registration_number"],
                    legal_name=est["legal_name"], office_id=est["office_id"], **public_fields(est),
                    pan=est["pan"], gstin=est.get("gstin"),
                    status=est["status"]))
                owner = next(u for u in seed["employer_users"] if u["role"] == "employer.owner")
                await s.execute(registration_requests.insert().values(
                    request_id="REQ-DEMO-0001", establishment_id=est["establishment_id"], owner_subject=owner["subject"],
                    state="SUBMITTED"))
                # Only the owner starts with permissions; Journey A2 adds the operator and the signatory.
                await s.execute(grants.insert().values(
                    grant_id="GR-OWNER-0001", establishment_id=est["establishment_id"], subject=owner["subject"],
                    username=owner["username"], kind="OWNER", grants=owner["grants"], status="ACTIVE",
                    granted_by="seed"))
            else:
                existing = (await s.execute(select(establishments).where(
                    establishments.c.establishment_id == est["establishment_id"]))).mappings().one()
                missing = {name: value for name, value in public_fields(est).items()
                           if value is not None and existing[name] is None}
                if missing:
                    await s.execute(update(establishments).where(
                        establishments.c.establishment_id == est["establishment_id"]).values(**missing))
            for public_est in seed.get("public_establishments", []):
                existing = (await s.execute(select(establishments).where(
                    establishments.c.establishment_id == public_est["establishment_id"]))).mappings().first()
                if not existing:
                    values = dict(public_est)
                    if values.get("verified_at"):
                        values["verified_at"] = datetime.fromisoformat(values["verified_at"])
                    values.update(public_fields(public_est))
                    await s.execute(establishments.insert().values(**values))
                else:
                    missing = {name: value for name, value in public_fields(public_est).items()
                               if value is not None and existing[name] is None}
                    if missing:
                        await s.execute(update(establishments).where(
                            establishments.c.establishment_id == public_est["establishment_id"]).values(**missing))
            profile = {k: est.get(k) for k in ("address", "kyc", "bank_accounts")}    # P2.6: set once, then changed by requests
            current = (await s.execute(select(establishments).where(establishments.c.establishment_id == est["establishment_id"]))).mappings().one()
            unset = {k: v for k, v in profile.items() if v is not None and current[k] is None}
            if unset:
                await s.execute(update(establishments).where(establishments.c.establishment_id == est["establishment_id"]).values(**unset))
            for st in seed.get("office_staff", []):
                if not (await s.execute(select(office_staff.c.subject).where(office_staff.c.subject == st["subject"]))).first():
                    await s.execute(office_staff.insert().values(subject=st["subject"], stakeholder=st["stakeholder"], office_id=st["office_id"]))
            for username, subject in seed["keycloak_subjects"].items():
                if not (await s.execute(select(directory.c.username).where(directory.c.username == username))).first():
                    role = next((u["role"] for u in seed["employer_users"] if u["username"] == username), "other")
                    await s.execute(directory.insert().values(username=username, subject=subject, role=role))
    print(f"employer-service seeded: {est['establishment_id']} ({est['status']}), owner grant, user directory")


if __name__ == "__main__":
    asyncio.run(main())
