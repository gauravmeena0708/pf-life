"""Pensioner services and office updation (Phase 2, slice 3), all illustrative.

* Life certificate: a Digital Life Certificate (mock Jeevan Pramaan, face authentication) or a physical one
  recorded at the PRO counter keeps the pension in payment for a year. A lapsed certificate lets the APFC
  (Pension) suspend the pension; resuming it releases the months held back.
* Updation activities: the DA (Pension) initiates one (basic details, pension start / stop, DLC revalidation,
  unhold transactions; the PRO counter's physical LC, death, spouse remarriage), the APFC (Pension) settles it
  — maker ≠ checker — and only then does it change the pension."""
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pension import catch_up_payments, today
from app.infra.tables import family_members, pensioners

LC_VALIDITY_DAYS = 365
DA_ACTIVITIES = {"BASIC_DETAILS", "PENSION_START", "PENSION_STOP", "DLC_REVALIDATION", "UNHOLD_TRANSACTIONS"}
PRO_ACTIVITIES = {"PHYSICAL_LC", "DEATH", "SPOUSE_REMARRIAGE"}


async def load(session: AsyncSession, ppo_id: str) -> dict[str, Any] | None:
    row = (await session.execute(select(pensioners).where(pensioners.c.ppo_id == ppo_id))).mappings().first()
    return dict(row) if row else None


def lc_state(p: dict[str, Any], on: date | None = None) -> str:
    valid = p.get("life_certificate_valid_till")
    return "VALID" if valid and valid >= (on or today()) else "EXPIRED"


async def renew_life_certificate(session: AsyncSession, p: dict[str, Any], source: str, ref: str) -> date:
    valid = today() + timedelta(days=LC_VALIDITY_DAYS)
    await session.execute(update(pensioners).where(pensioners.c.ppo_id == p["ppo_id"]).values(
        life_certificate_valid_till=valid, life_certificate_source=source, life_certificate_ref=ref))
    return valid


async def set_status(session: AsyncSession, p: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    """Suspend / stop / resume. Credits up to now are made first; on resumption the held months are released."""
    if status != "IN_PAYMENT":
        await catch_up_payments(session, p)                      # months already due are paid before the hold
    await session.execute(update(pensioners).where(pensioners.c.ppo_id == p["ppo_id"]).values(status=status, status_reason=reason))
    p = {**p, "status": status, "status_reason": reason}
    if status == "IN_PAYMENT":
        await catch_up_payments(session, p, released_on=today())
    return p


async def apply_activity(session: AsyncSession, activity: dict[str, Any]) -> str:
    """What a settled activity does to the pension; returns a line for the tracker."""
    p = await load(session, activity["ppo_id"])
    kind, d = activity["activity"], activity["details"] or {}
    if kind in ("DLC_REVALIDATION", "PHYSICAL_LC"):
        valid = await renew_life_certificate(session, p, "PHYSICAL" if kind == "PHYSICAL_LC" else "OFFICE_REVALIDATION", activity["activity_id"])
        if p["status"] == "SUSPENDED":
            await set_status(session, p, "IN_PAYMENT", "Life certificate received")
        return f"Life certificate valid till {valid.isoformat()}."
    if kind in ("PENSION_START", "UNHOLD_TRANSACTIONS"):
        await set_status(session, p, "IN_PAYMENT", d.get("reason") or kind.replace("_", " ").lower())
        return "Pension in payment; months held back are credited."
    if kind == "PENSION_STOP":
        await set_status(session, p, "STOPPED", d.get("reason") or "Stopped by the office")
        return "Pension stopped."
    if kind == "DEATH":
        await set_status(session, p, "STOPPED", f"Death on {d.get('date_of_death', '—')}; family pension to be settled")
        if p.get("pension_kind") == "FATHER" and d.get("date_of_death"):
            # EPS para 16(5)(aa): the dependent mother succeeds the father after his death.
            await session.execute(update(family_members).where(family_members.c.uan == p["uan"],
                              family_members.c.subject == p["subject"], family_members.c.relation == "FATHER").values(
                              date_of_death=date.fromisoformat(d["date_of_death"])))
        return "Pension stopped on the pensioner's death."
    if kind == "BASIC_DETAILS":
        values = {k: v for k, v in (("bank_ifsc", d.get("bank_ifsc")), ("bank_account_last4", d.get("bank_account_last4"))) if v}
        if d.get("name"):
            values["name"] = str(d["name"]).upper()
        if values:
            await session.execute(update(pensioners).where(pensioners.c.ppo_id == p["ppo_id"]).values(**values))
        return "Details updated: " + ", ".join(sorted(values)) if values else "No change."
    if kind == "SPOUSE_REMARRIAGE":
        return "Recorded (family pension to the spouse ends; not modelled in this demonstration)."
    return "Recorded."
