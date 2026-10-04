"""Events about one demand applied in either order: the copy keeps the latest state (CI found a 7A demand left OPEN here
after contribution-service had withdrawn it — the OPEN event was re-queued behind the WITHDRAWN one)."""
import asyncio
import uuid

from tests.test_compliance import EST, ctx  # noqa: F401  (ctx is a fixture)


def state_change(demand_id, state, at):
    return {"event_id": str(uuid.uuid4()), "event_type": "DemandStateChanged.v1", "correlation_id": str(uuid.uuid4()),
            "occurred_at": at, "payload": {"demand_id": demand_id, "establishment_id": EST, "kind": "DUES_7A", "trrn": "-",
                                           "wage_month": "-", "amount_paise": 4500000, "days_late": 0, "state": state, "working": "7A order"}}


def apply(event):
    import app.infra.db as db
    from app.infra.messaging import dispatch
    from epfo_persistence.consumer import apply_once
    asyncio.run(apply_once(db.sessions(), event, dispatch))


def test_the_later_state_wins_whatever_the_order(ctx):
    _, q, _ = ctx
    opened, withdrawn = "2026-10-04T22:00:00.100000Z", "2026-10-04T22:00:00.900000Z"
    apply(state_change("D7A-LATE-OPEN", "WITHDRAWN", withdrawn))       # the withdrawal arrives first …
    apply(state_change("D7A-LATE-OPEN", "OPEN", opened))               # … the order's own OPEN after it
    apply(state_change("D7A-IN-ORDER", "OPEN", opened))
    apply(state_change("D7A-IN-ORDER", "WITHDRAWN", withdrawn))
    rows = dict(q("SELECT demand_id, state FROM demands WHERE demand_id IN ('D7A-LATE-OPEN', 'D7A-IN-ORDER')"))
    assert rows == {"D7A-LATE-OPEN": "WITHDRAWN", "D7A-IN-ORDER": "WITHDRAWN"}
