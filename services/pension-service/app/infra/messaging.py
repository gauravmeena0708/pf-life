"""Event consumers: a published rule set is stored, then pensions in payment are recomputed under it; a pension
updation inwarded on paper at the PRO counter becomes a NEW activity on the pension office's tracker."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import propose_revisions
from app.infra.tables import eps_accounts, eps_transfers, exempted_establishments, higher_pension_options, pensioners, updation_activities
from epfo_persistence import add_event
from epfo_persistence.policy import on_policy_published

BINDINGS = ["platform-service.PolicyPublished.v1", "claim-service.PhysicalClaimInwarded.v1", "workflow-service.StaffPostingChanged.v1",
            "employer-service.ExemptionStatusChanged.v1",
            "contribution-service.HigherPensionTransferPosted.v1", "member-service.MemberRegistered.v1",
            "member-service.MemberExitMarked.v1", "member-service.PrimaryMemberIdChanged.v1", "member-service.MemberDeathRecorded.v1",
            "contribution-service.EpsRectified.v1",
            "contribution-service.TransferPosted.v1"]
# PRO counter request → updation activity. PPO amendments are basic-details updations the DA (Pension) takes up.
INTAKE_ACTIVITIES = {"PHYSICAL_LC_UPDATION": "PHYSICAL_LC", "DEATH_UPDATION": "DEATH", "SPOUSE_REMARRIAGE_UPDATION": "SPOUSE_REMARRIAGE",
                     "PPO_AMENDMENT_BENEFICIARY": "BASIC_DETAILS", "PPO_AMENDMENT_SERVICE": "BASIC_DETAILS", "PPO_AMENDMENT_POHW": "BASIC_DETAILS"}


async def on_physical_intake(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    activity = INTAKE_ACTIVITIES.get(p["form_type"])
    if not activity or not (await session.execute(select(pensioners.c.ppo_id).where(pensioners.c.ppo_id == p["ppo_id"]))).first():
        return                                            # not a pension updation, or an unknown PPO: nothing to track
    activity_id = f"UPD-{p['intake_id']}"
    if (await session.execute(select(updation_activities.c.activity_id).where(updation_activities.c.activity_id == activity_id))).first():
        return                                            # redelivered
    now = datetime.now(UTC)
    await session.execute(insert(updation_activities).values(
        activity_id=activity_id, ppo_id=p["ppo_id"], activity=activity, mode="PHYSICAL", status="NEW",
        details={**p["details"], "intake_id": p["intake_id"], "form_type": p["form_type"], "filed_by": p["filed_by"]},
        initiated_by="pro-counter", initiated_role="fo.pro_intake", created_at=now, updated_at=now))


async def on_higher_pension_transfer(session: AsyncSession, event: dict[str, Any]) -> None:
    payload = event["payload"]
    row = (await session.execute(select(higher_pension_options).where(
        higher_pension_options.c.option_id == payload["option_id"]).with_for_update())).mappings().first()
    if not row or row["state"] != "TRANSFER_REQUESTED" or payload.get("status") not in ("POSTED", "INSUFFICIENT_BALANCE"):
        return
    state = "DUES_TRANSFERRED" if payload["status"] == "POSTED" else "TRANSFER_FAILED"
    await session.execute(update(higher_pension_options).where(higher_pension_options.c.option_id == row["option_id"]).values(state=state))
    await add_event(session, producer="pension-service", event_type="NotificationRequested.v1", aggregate_type="notification",
                    aggregate_id=row["option_id"], correlation_id=event["correlation_id"], payload={
                        "recipient_subject": row["subject"], "template": "HIGHER_PENSION_" + state,
                        "reference_id": row["option_id"], "params": {"amount_paise": row["dues_paise"],
                        "reason": "The member deposits the difference through the office (VDR)." if state == "TRANSFER_FAILED" else ""}})


async def on_member_registered(session: AsyncSession, event: dict[str, Any]) -> None:
    """A new member ID opens its EPS account; it joins the UAN's existing group (P2.9b)."""
    p = event["payload"]
    if (await session.execute(select(eps_accounts.c.account_link_id).where(eps_accounts.c.account_link_id == p["account_link_id"]))).first():
        return
    key = (await session.execute(select(eps_accounts.c.person_key).where(eps_accounts.c.uan == p["uan"]).limit(1))).scalar_one_or_none()
    await session.execute(insert(eps_accounts).values(
        account_link_id=p["account_link_id"], uan=p["uan"], person_key=key or p["uan"], establishment_id=p.get("establishment_id"),
        date_of_joining=date.fromisoformat(p["date_of_joining"])))


async def on_member_exit(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    await session.execute(update(eps_accounts).where(eps_accounts.c.account_link_id == p["account_link_id"]).values(
        date_of_exit=date.fromisoformat(p["date_of_exit"]), exit_reason=p.get("reason")))


async def on_primary_changed(session: AsyncSession, event: dict[str, Any]) -> None:
    """The member's Aadhaar-verified set of UANs is one person: their EPS accounts form one group."""
    uans = sorted(set(event["payload"].get("set_uans") or []) | {event["payload"]["uan"]})
    await session.execute(update(eps_accounts).where(eps_accounts.c.uan.in_(uans)).values(person_key="SET-" + uans[0]))


async def on_transfer_posted(session: AsyncSession, event: dict[str, Any]) -> None:
    """A PF posting completes the EPS leg, including a transfer involving an exempted trust."""
    p = event["payload"]
    transfer_id = p["transfer_id"]
    if (await session.execute(select(eps_transfers.c.transfer_id).where(eps_transfers.c.transfer_id == transfer_id))).first():
        return
    frm, to = p["from_account_link_id"], p["to_account_link_id"]
    source = (await session.execute(select(eps_accounts).where(eps_accounts.c.account_link_id == frm).with_for_update())).mappings().first()
    destination = (await session.execute(select(eps_accounts).where(eps_accounts.c.account_link_id == to))).mappings().first()
    if not source or not destination or source["person_key"] != destination["person_key"]:
        raise ValueError(f"EPS transfer {transfer_id} has missing or unrelated member IDs")
    service_from = date.fromisoformat(p["service_from"]) if p.get("service_from") else source["date_of_joining"]
    service_to = date.fromisoformat(p["service_to"]) if p.get("service_to") else source["date_of_exit"] or date.today()
    service_months = max(0, (service_to.year - service_from.year) * 12 + service_to.month - service_from.month
                         - (service_to.day < service_from.day))
    breaks_months = int(p["breaks_months"]) if p.get("breaks_months") is not None else int(source["breaks_months"])
    if breaks_months < 0 or service_to < service_from:
        raise ValueError(f"EPS transfer {transfer_id} has invalid service dates or breaks")
    await session.execute(insert(eps_transfers).values(
        transfer_id=transfer_id, from_account_link_id=frm, to_account_link_id=to,
        service_months=service_months, breaks_months=breaks_months, transferred_at=datetime.now(UTC)))
    await session.execute(update(eps_accounts).where(eps_accounts.c.account_link_id == frm).values(
        transferred_to=to, breaks_months=breaks_months))
    await add_event(session, producer="pension-service", event_type="EpsServiceTransferred.v1", aggregate_type="transfer",
                    aggregate_id=transfer_id, correlation_id=event["correlation_id"], payload={
                        "transfer_id": transfer_id, "from_account_link_id": frm, "to_account_link_id": to,
                        "service_months": service_months, "breaks_months": breaks_months})


async def on_exemption_status_changed(session: AsyncSession, event: dict[str, Any]) -> None:
    p = event["payload"]
    if p["status"] not in ("ACTIVE", "UNEXEMPTED_COMPLIANCE", "SURRENDERED", "CANCELLED"):
        raise ValueError(f"Unknown exemption status: {p['status']}")
    await session.execute(update(exempted_establishments).where(
        exempted_establishments.c.establishment_id == p["establishment_id"]).values(
            status=p["status"], ended_on=date.fromisoformat(p["ended_on"]) if p.get("ended_on") else None))


async def on_member_death(session: AsyncSession, event: dict[str, Any]) -> None:
    """P2.21b: a death on record (from the employer's exit or the civil registry's feed). A pension in payment to the member
    stops from the death — not on a missing life certificate months later — and the date of death is kept so the family
    may apply for the family pension (Form 10D) without waiting for a PRO counter updation."""
    from app.infra.tables import member_service
    p = event["payload"]
    died = date.fromisoformat(p["date_of_death"])
    await session.execute(update(member_service).where(member_service.c.uan == p["uan"], member_service.c.date_of_exit.is_(None))
                          .values(date_of_exit=died))
    source = "the civil registry" + (f" (registration {p['registration_no']})" if p.get("registration_no") else "") \
        if p["source"] == "CIVIL_REGISTRY" else p["source"].lower()
    born = (await session.execute(select(member_service.c.date_of_birth).where(member_service.c.uan == p["uan"]))).scalars().first()
    # the member's own pension only: a family pension on the same UAN is paid to someone born on another day
    await session.execute(update(pensioners).where(pensioners.c.uan == p["uan"], pensioners.c.date_of_birth == born,
                                                   pensioners.c.status.in_(("IN_PAYMENT", "SUSPENDED")))
                          .values(status="STOPPED", status_reason=f"Death on {died.isoformat()} reported by {source}; "
                                                                  "the family pension is settled on Form 10D, and any pension credited after the death is recovered"))


async def on_eps_rectified(session: AsyncSession, event: dict[str, Any]) -> None:
    """P2.19c (HO circular WSU/2025/E-961539): EPS wrongly allowed — the member ID's pension service is deleted; EPS wrongly
    denied — it is credited (with any non-contributory period: the service counts from joining to exit)."""
    p = event["payload"]
    await session.execute(update(eps_accounts).where(eps_accounts.c.account_link_id == p["account_link_id"])
                          .values(eps_member=p["scenario"] == "WRONGLY_DENIED"))


HANDLERS = {"ExemptionStatusChanged.v1": on_exemption_status_changed, "MemberDeathRecorded.v1": on_member_death, "EpsRectified.v1": on_eps_rectified,
            "HigherPensionTransferPosted.v1": on_higher_pension_transfer, "MemberRegistered.v1": on_member_registered,
            "MemberExitMarked.v1": on_member_exit, "PrimaryMemberIdChanged.v1": on_primary_changed,
            "TransferPosted.v1": on_transfer_posted}


async def dispatch(session: AsyncSession, event: dict[str, Any]) -> None:
    if handler := HANDLERS.get(event["event_type"]):
        await handler(session, event)
        return
    if event["event_type"] == "StaffPostingChanged.v1":           # HR re-posted an officer (P2.8e)
        from app.infra.tables import office_staff
        from epfo_persistence.postings import apply_posting
        await apply_posting(session, event, office_staff)
        return
    if event["event_type"] == "PhysicalClaimInwarded.v1":
        await on_physical_intake(session, event)
    if event["event_type"] == "PolicyPublished.v1":
        await on_policy_published(session, event)
        p = event["payload"]
        await propose_revisions(session, p["document"], date.fromisoformat(p["effective_from"]))
