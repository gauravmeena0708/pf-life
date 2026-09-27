"""Load deterministic synthetic seed data (scripts/seed/synthetic.json). Idempotent: python -m app.seed"""
import asyncio
import json
import os

from sqlalchemy import select

from app.infra.db import sessions
from app.infra.tables import directory, establishments, grants, registration_requests

SEED_FILE = os.environ.get("SEED_FILE", "/srv/seed/synthetic.json")


async def main() -> None:
    seed = json.load(open(SEED_FILE, encoding="utf-8"))
    est = seed["establishment"]
    async with sessions()() as s:
        async with s.begin():
            if not (await s.execute(select(establishments.c.establishment_id).where(
                    establishments.c.establishment_id == est["establishment_id"]))).first():
                await s.execute(establishments.insert().values(
                    establishment_id=est["establishment_id"], registration_number=est["registration_number"],
                    legal_name=est["legal_name"], office_id=est["office_id"], pan=est["pan"], gstin=est.get("gstin"),
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
            for username, subject in seed["keycloak_subjects"].items():
                if not (await s.execute(select(directory.c.username).where(directory.c.username == username))).first():
                    role = next((u["role"] for u in seed["employer_users"] if u["username"] == username), "other")
                    await s.execute(directory.insert().values(username=username, subject=subject, role=role))
    print(f"employer-service seeded: {est['establishment_id']} ({est['status']}), owner grant, user directory")


if __name__ == "__main__":
    asyncio.run(main())
