"""Demands (14B damages, 7Q interest) as other services see them (Phase 2, slice 8a): every change is published as
DemandStateChanged.v1 — compliance-service projects them for VISHWAS, the mock bank for paying a demand directly.
A VISHWAS decision (DemandRaised.v1 from compliance-service) replaces the demands it covers with one revised demand;
a demand paid directly (PaymentConfirmed.v1, purpose DEMAND) is posted to the ledger and closed."""
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, text

from epfo_persistence import add_event

PRODUCER = "contribution-service"


async def publish(session, demand_ids: list[str], correlation_id: str | None) -> None:
    if not demand_ids:
        return
    rows = (await session.execute(text("SELECT * FROM demands WHERE demand_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                                  {"ids": list(demand_ids)})).mappings().all()
    for d in rows:
        await add_event(session, producer=PRODUCER, event_type="DemandStateChanged.v1", aggregate_type="demand", aggregate_id=d["demand_id"],
                        correlation_id=correlation_id, payload={
                            "demand_id": d["demand_id"], "establishment_id": d["establishment_id"], "kind": d["kind"], "trrn": d["trrn"],
                            "wage_month": d["wage_month"], "amount_paise": int(d["amount_paise"]), "days_late": int(d["days_late"]),
                            "state": d["state"], "working": d["working"]})


async def on_demand_raised(session, event: dict[str, Any]) -> None:
    """Create a VISHWAS revised demand or a section 7A dues demand."""
    p = event["payload"]
    if (await session.execute(text("SELECT 1 FROM demands WHERE demand_id=:d"), {"d": p["demand_id"]})).first():
        return
    covered = list(p.get("supersedes_demand_ids") or [])
    if p.get("withdraw") or int(p.get("amount_paise", 0)) == 0:
        if covered:
            await session.execute(text("UPDATE demands SET state='WITHDRAWN', settled_by=:by WHERE demand_id IN :ids AND state='OPEN'")
                                  .bindparams(bindparam("ids", expanding=True)), {"by": p["demand_id"], "ids": covered})
        await publish(session, covered, event.get("correlation_id"))
        return
    first = (await session.execute(text("SELECT * FROM demands WHERE demand_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                                   {"ids": covered or ["-"]})).mappings().first()
    kind = "DUES_7A" if p.get("demand_type") == "DUES_7A" else ("INTEREST_7Q" if p.get("demand_type") == "INTEREST_7Q" else "DAMAGES_14B")
    await session.execute(text("INSERT INTO demands (demand_id,establishment_id,kind,trrn,wage_month,amount_paise,days_late,working,rule_version,state,created_at) "
                               "VALUES (:d,:e,:k,:t,:m,:a,:days,:w,:r,'OPEN',:at)"),
                          {"d": p["demand_id"], "e": p["establishment_id"], "k": kind, "t": first["trrn"] if first else "-",
                           "m": first["wage_month"] if first else "-", "a": int(p["amount_paise"]), "days": first["days_late"] if first else 0,
                           "w": p.get("working") or "Revised under VISHWAS", "r": p.get("rule_version") or "-", "at": datetime.now(UTC)})
    if covered:
        await session.execute(text("UPDATE demands SET state='WAIVED', settled_by=:by WHERE demand_id IN :ids AND state='OPEN'")
                              .bindparams(bindparam("ids", expanding=True)), {"by": p["demand_id"], "ids": covered})
    await publish(session, [p["demand_id"], *covered], event.get("correlation_id"))


async def on_demand_paid(session, event: dict[str, Any]) -> None:
    """A demand paid directly through the mock bank: the ledger records the receipt; the demand is closed."""
    p = event["payload"]
    d = (await session.execute(text("SELECT * FROM demands WHERE demand_id=:d"), {"d": p["reference_id"]})).mappings().first()
    if not d or d["state"] != "OPEN" or int(p["amount_paise"]) != int(d["amount_paise"]):
        return
    if not (await session.execute(text("SELECT 1 FROM journals WHERE business_key=:k"), {"k": p["payment_id"]})).first():
        jid = str(uuid.uuid4())
        await session.execute(text("INSERT INTO journals (id,business_key,kind,occurred_at) VALUES (:id,:k,'DEMAND_PAYMENT',:at)"),
                              {"id": jid, "k": p["payment_id"], "at": datetime.now(UTC)})
        credits = [(d["kind"], int(d["amount_paise"]))]
        if d["kind"] == "DUES_7A":
            dues = json.loads(d["working"] or "[]")
            credits = [(code, sum(int(row[key]) for row in dues)) for code, key in (
                ("AC01_EPF", "ac1_employee_paise"), ("AC01_EPF", "ac1_employer_paise"),
                ("AC10_EPS", "ac10_pension_paise"), ("AC21_EDLI", "ac21_edli_paise"),
                ("AC02_ADMIN", "ac2_admin_paise"))]
            grouped = {}
            for code, amount in credits:
                grouped[code] = grouped.get(code, 0) + amount
            credits = [(code, amount) for code, amount in grouped.items() if amount]
            if sum(amount for _, amount in credits) != int(d["amount_paise"]):
                raise ValueError("7A demand working does not reconcile to its total")
        for code, side, amount in [("BANK_COLLECTION", "debit", int(d["amount_paise"])),
                                   *((code, "credit", amount) for code, amount in credits)]:
            await session.execute(text("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise) VALUES (:j,:a,:s,:n)"),
                                  {"j": jid, "a": code, "s": side, "n": amount})
    await session.execute(text("UPDATE demands SET state='PAID', settled_by=:p WHERE demand_id=:d"), {"p": p["payment_id"], "d": d["demand_id"]})
    await publish(session, [d["demand_id"]], event.get("correlation_id"))


async def on_recovery_realised(session, event: dict[str, Any]) -> None:
    """Money the Recovery Officer realised against open demands (RecoveryRealised.v1 from compliance-service)."""
    p = event["payload"]
    reference = p.get("reference")
    if not reference:
        return
    business_key = f"RECOVERY-{reference}"
    remaining = int(p.get("amount_paise") or 0)
    demand_ids = list(p.get("demand_ids") or [])
    if remaining <= 0 or not demand_ids:
        return
    # Realisations arrive together (a sale, an 8F payment, a cheque) and the consumer applies them concurrently: lock the
    # demands first, so each one reads the amount already realised by the others (no lost update), then check the reference.
    lock = " ORDER BY demand_id FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""
    rows = (await session.execute(
        text("SELECT * FROM demands WHERE demand_id IN :ids" + lock).bindparams(bindparam("ids", expanding=True)),
        {"ids": demand_ids}
    )).mappings().all()
    if (await session.execute(text("SELECT 1 FROM journals WHERE business_key=:k"), {"k": business_key})).first():
        return
    demands_by_id = {r["demand_id"]: dict(r) for r in rows}

    credits_by_account: dict[str, int] = {}
    changed_demands: list[tuple[dict[str, Any], int, int]] = []

    for did in demand_ids:
        if remaining <= 0:
            break
        d = demands_by_id.get(did)
        if not d or d["state"] != "OPEN":
            continue
        amt = int(d["amount_paise"])
        realised = int(d.get("realised_paise") or 0)
        unrealised = amt - realised
        if unrealised <= 0:
            continue
        applied = min(remaining, unrealised)
        if applied <= 0:
            continue
        remaining -= applied
        new_realised = realised + applied
        d["realised_paise"] = new_realised
        changed_demands.append((d, applied, new_realised))

        if d["kind"] == "DUES_7A":
            dues = json.loads(d["working"] or "[]") if isinstance(d["working"], str) else (d["working"] or [])
            parts = [
                ("AC01_EPF", sum(int(row.get("ac1_employee_paise", 0)) + int(row.get("ac1_employer_paise", 0)) for row in dues)),
                ("AC10_EPS", sum(int(row.get("ac10_pension_paise", 0)) for row in dues)),
                ("AC21_EDLI", sum(int(row.get("ac21_edli_paise", 0)) for row in dues)),
                ("AC02_ADMIN", sum(int(row.get("ac2_admin_paise", 0)) for row in dues)),
            ]
            total_weight = sum(w for _, w in parts)
            if total_weight > 0:
                floors = {code: (applied * w) // total_weight for code, w in parts}
                rems = {code: (applied * w) % total_weight for code, w in parts}
                diff = applied - sum(floors.values())
                order = sorted([code for code, _ in parts], key=lambda c: rems[c], reverse=True)
                for code in order[:diff]:
                    floors[code] += 1
                for code, share in floors.items():
                    if share:
                        credits_by_account[code] = credits_by_account.get(code, 0) + share
            else:
                credits_by_account[d["kind"]] = credits_by_account.get(d["kind"], 0) + applied
        else:
            code = d["kind"]
            credits_by_account[code] = credits_by_account.get(code, 0) + applied

    total_applied = sum(applied for _, applied, _ in changed_demands)
    if total_applied <= 0:
        return

    jid = str(uuid.uuid4())
    await session.execute(
        text("INSERT INTO journals (id,business_key,kind,occurred_at) VALUES (:id,:k,'RECOVERY_REALISATION',:at)"),
        {"id": jid, "k": business_key, "at": datetime.now(UTC)}
    )
    await session.execute(
        text("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise) VALUES (:j,'BANK_COLLECTION','debit',:n)"),
        {"j": jid, "n": total_applied}
    )
    for code, amount in credits_by_account.items():
        if amount > 0:
            await session.execute(
                text("INSERT INTO journal_lines (journal_id,account_code,side,amount_paise) VALUES (:j,:a,'credit',:n)"),
                {"j": jid, "a": code, "n": amount}
            )

    for d, _, new_realised in changed_demands:
        amt = int(d["amount_paise"])
        if new_realised >= amt:
            await session.execute(
                text("UPDATE demands SET realised_paise=:r, state='PAID', settled_by=:s WHERE demand_id=:d"),
                {"r": new_realised, "s": reference, "d": d["demand_id"]}
            )
        else:
            await session.execute(
                text("UPDATE demands SET realised_paise=:r WHERE demand_id=:d"),
                {"r": new_realised, "d": d["demand_id"]}
            )

    changed_ids = list(dict.fromkeys(d["demand_id"] for d, _, _ in changed_demands))
    await publish(session, changed_ids, event.get("correlation_id"))

