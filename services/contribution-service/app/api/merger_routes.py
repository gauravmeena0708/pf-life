"""Office record of an establishment amalgamation without a service break."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.infra.db import sessions
from epfo_auth import Actor, require_stakeholder
from epfo_observability import Problem, envelope
from epfo_persistence import audit

router = APIRouter()


class Merger(BaseModel):
    from_establishment_id: str
    to_establishment_id: str
    effective_on: date


@router.post("/api/v1/office/establishments/mergers")
async def merge(body: Merger, actor: Actor = Depends(require_stakeholder("fo.oic", "fo.apfc"))) -> dict:
    frm, to = body.from_establishment_id, body.to_establishment_id
    if frm == to:
        raise Problem(422, "/problems/validation", "Transferor and transferee must differ")
    async with sessions()() as session, session.begin():
        establishments = (await session.execute(text("SELECT id FROM establishments WHERE id IN (:f,:t)"),
                                                {"f": frm, "t": to})).scalars().all()
        if len(establishments) != 2:
            raise Problem(404, "/problems/not-found", "An establishment was not found")
        previous = (await session.execute(text("SELECT to_establishment_id,effective_on FROM establishment_mergers "
                                               "WHERE from_establishment_id=:f"), {"f": frm})).mappings().first()
        if previous:
            if previous["to_establishment_id"] != to or str(previous["effective_on"])[:10] != body.effective_on.isoformat():
                raise Problem(409, "/problems/already-merged", "A different merger is already recorded")
            return envelope({"from_establishment_id": frm, "to_establishment_id": to,
                             "effective_on": body.effective_on.isoformat(), "already_recorded": True})
        await session.execute(text("INSERT INTO establishment_mergers "
                                   "(from_establishment_id,to_establishment_id,effective_on,recorded_by) "
                                   "VALUES (:f,:t,:d,:by)"),
                              {"f": frm, "t": to, "d": body.effective_on, "by": actor.subject})
        # EPF amalgamation: the same member ID and joining date carry on without a Form 13 claim.
        members = await session.execute(text("UPDATE establishment_members SET establishment_id=:t "
                                             "WHERE establishment_id=:f AND date_of_exit IS NULL"), {"f": frm, "t": to})
        demands = await session.execute(text("UPDATE demands SET establishment_id=:t "
                                             "WHERE establishment_id=:f AND state='OPEN'"), {"f": frm, "t": to})
        await session.execute(text("UPDATE challans SET establishment_id=:t WHERE establishment_id=:f "
                                   "AND status IN ('DUE','FAILED')"), {"f": frm, "t": to})
        await session.execute(text("UPDATE establishments SET closed_on=:d, "
                                   "last_wage_month=:m WHERE id=:f"),
                              {"d": body.effective_on, "m": f"{body.effective_on.year:04d}-{body.effective_on.month:02d}",
                               "f": frm})
        await audit(session, actor_subject=actor.subject, actor_stakeholder=actor.stakeholder,
                    action="establishment.merged", target_type="establishment", target_id=frm,
                    detail=f"to={to}; effective_on={body.effective_on.isoformat()}")
    return envelope({"from_establishment_id": frm, "to_establishment_id": to,
                     "effective_on": body.effective_on.isoformat(), "members": members.rowcount,
                     "demands": demands.rowcount})
