"""Load deterministic synthetic seed data (scripts/seed/synthetic.json). Idempotent: python -m app.seed"""
import asyncio
import json
import os
from datetime import date, datetime

from sqlalchemy import select, update

from app.infra.db import sessions
from app.infra.tables import (contractors, directory, establishment_exemptions, establishments, grants,
                              office_staff, offices, registration_requests)

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
            for exemption in ([seed["exempted_establishment"]] if seed.get("exempted_establishment") else []) + seed.get("more_exempted_establishments", {}).get("establishments", []):
              if not (await s.execute(select(establishment_exemptions.c.establishment_id).where(
                    establishment_exemptions.c.establishment_id == exemption["establishment_id"]))).first():
                await s.execute(establishment_exemptions.insert().values(
                    establishment_id=exemption["establishment_id"], kind=exemption["kind"],
                    pf_exempt=exemption["pf_exempt"], pension_exempt=exemption["pension_exempt"],
                    edli_exempt=exemption["edli_exempt"], notification_no=exemption["notification_no"],
                    notification_date=date.fromisoformat(exemption["notification_date"]),
                    effective_from=date.fromisoformat(exemption["effective_from"]), status=exemption["status"],
                    trust_id=exemption["trust_id"], trust_name=exemption["trust_name"],
                    trust_users=exemption["trust_users"]))
            profile = {k: est.get(k) for k in ("address", "kyc", "bank_accounts")}    # P2.6: set once, then changed by requests
            current = (await s.execute(select(establishments).where(establishments.c.establishment_id == est["establishment_id"]))).mappings().one()
            unset = {k: v for k, v in profile.items() if v is not None and current[k] is None}
            if unset:
                await s.execute(update(establishments).where(establishments.c.establishment_id == est["establishment_id"]).values(**unset))
            for st in seed.get("office_staff", []):
                if not (await s.execute(select(office_staff.c.subject).where(office_staff.c.subject == st["subject"]))).first():
                    await s.execute(office_staff.insert().values(subject=st["subject"], stakeholder=st["stakeholder"], office_id=st["office_id"]))
            for office in [seed["office"], *seed.get("other_offices", [])]:
                existing_office = (await s.execute(select(offices).where(offices.c.office_id == office["office_id"]))).mappings().first()
                if not existing_office:
                    await s.execute(offices.insert().values(office_id=office["office_id"], name=office["name"], zone_id=office.get("zone_id")))
                elif not existing_office["zone_id"] and office.get("zone_id"):
                    await s.execute(update(offices).where(offices.c.office_id == office["office_id"]).values(zone_id=office["zone_id"]))
            principal = seed.get("principal_employer")
            if principal and (await s.execute(select(establishments.c.establishment_id).where(
                    establishments.c.establishment_id == principal["establishment_id"]))).first():
                if not (await s.execute(select(grants.c.grant_id).where(
                        grants.c.subject == principal["subject"], grants.c.establishment_id == principal["establishment_id"],
                        grants.c.kind == "OWNER"))).first():
                    await s.execute(grants.insert().values(
                        grant_id=f"GR-OWNER-{principal['establishment_id']}", establishment_id=principal["establishment_id"],
                        subject=principal["subject"], username=principal["username"], kind="OWNER",
                        grants=principal.get("grants", []), status="ACTIVE", granted_by="seed"))
            for extra in seed.get("extra_employer_grants", []):        # P2.9b: e.g. the signatory of an exempted establishment
                if (await s.execute(select(establishments.c.establishment_id).where(
                        establishments.c.establishment_id == extra["establishment_id"]))).first() and not (await s.execute(
                        select(grants.c.grant_id).where(grants.c.subject == extra["subject"],
                                                        grants.c.establishment_id == extra["establishment_id"],
                                                        grants.c.kind == extra["kind"]))).first():
                    await s.execute(grants.insert().values(
                        grant_id=f"GR-{extra['kind'][:3]}-{extra['establishment_id']}-{extra['username'][:8]}"[:40], establishment_id=extra["establishment_id"],
                        subject=extra["subject"], username=extra["username"], kind=extra["kind"], grants=extra.get("grants", []),
                        status="ACTIVE", granted_by="seed"))
            for link in seed.get("contractor_links", []):
                principal_est = (await s.execute(select(establishments).where(
                    establishments.c.establishment_id == link["principal_establishment_id"]))).mappings().first()
                contractor_est = (await s.execute(select(establishments).where(
                    establishments.c.establishment_id == link["contractor_establishment_id"]))).mappings().first()
                if not principal_est or not contractor_est:
                    continue
                if not (await s.execute(select(contractors.c.contractor_id).where(
                        contractors.c.principal_establishment_id == link["principal_establishment_id"],
                        contractors.c.contractor_establishment_id == link["contractor_establishment_id"],
                        contractors.c.work_order_ref == link["work_order_ref"]))).first():
                    await s.execute(contractors.insert().values(
                        contractor_id=f"CTR-SEED-{len(link['work_order_ref'])}-{link['contractor_establishment_id']}",
                        principal_establishment_id=link["principal_establishment_id"],
                        contractor_establishment_id=link["contractor_establishment_id"],
                        contractor_registration_number=contractor_est["registration_number"], contractor_name=contractor_est["legal_name"],
                        work_order_ref=link["work_order_ref"], valid_from=date.fromisoformat(link["valid_from"]),
                        linked_by="seed"))
            for username, subject in seed["keycloak_subjects"].items():
                if not (await s.execute(select(directory.c.username).where(directory.c.username == username))).first():
                    role = next((u["role"] for u in [*seed["employer_users"], *seed.get("extra_employer_grants", [])]
                                 if u["username"] == username), "exempted.trust" if any(
                                     u["username"] == username for ex in [seed.get("exempted_establishment"), *seed.get("more_exempted_establishments", {}).get("establishments", [])]
                                     if ex for u in ex["trust_users"]) else "other")
                    await s.execute(directory.insert().values(username=username, subject=subject, role=role))
    print(f"employer-service seeded: {est['establishment_id']} ({est['status']}), owner grant, user directory")


if __name__ == "__main__":
    asyncio.run(main())
