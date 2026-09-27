"""Plain-language notices for synthetic claim events."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.tables import members, notifications

TEMPLATES = {
    "CLAIM_SUBMITTED": ("Claim submitted", "Your claim {reference_id} was submitted. We will tell you when it moves forward."),
    "CLAIM_UNDER_REVIEW": ("Claim under review", "Your claim {reference_id} is being reviewed."),
    "CLAIM_APPROVED": ("Claim approved", "Your claim {reference_id}{amount} was approved. Payment is being arranged."),
    "CLAIM_REJECTED": ("Claim rejected", "Your claim {reference_id} was rejected. {reason}"),
    "CLAIM_SETTLED": ("Claim paid", "Your claim {reference_id}{amount} was paid into your bank account{bank_ending}."),
    "CLAIM_PAYMENT_RETURNED": ("Claim payment returned", "The payment for your claim {reference_id} was returned by the bank. {reason}"),
    "CLAIM_REISSUED": ("Claim payment reissued", "Payment for your claim {reference_id} was reissued."),
}


def rupees(paise: int) -> str:
    """₹ with Indian digit grouping, e.g. 60000000 → ₹6,00,000."""
    whole, frac = divmod(paise, 100)
    digits = str(whole)
    if len(digits) > 3:
        head, groups = digits[:-3], [digits[-3:]]
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join(([head] if head else []) + groups)
    return f"₹{digits}" + (f".{frac:02d}" if frac else "")


def render(template: str, reference_id: str, params: dict[str, Any] | None = None) -> tuple[str, str]:
    title, body = TEMPLATES.get(template, ("Claim update", "There is an update about your claim {reference_id}."))
    values = params or {}
    ending = values.get("bank_account_last4")
    reason = str(values.get("reason") or "Check your claim details for more information.")
    paise = values.get("amount_paise")
    amount = f" for {rupees(int(paise))}" if paise is not None else ""
    return title, body.format(reference_id=reference_id, reason=reason,
                              amount=amount, bank_ending=f" ending {ending}" if ending else "")


async def handle_notification_requested(session: AsyncSession, event: dict[str, Any]) -> None:
    if (await session.execute(select(notifications.c.id).where(
            notifications.c.event_id == event["event_id"]))).first():
        return
    payload = event["payload"]
    params = dict(payload.get("params") or {})
    if "bank_account_last4" not in params:   # the producer does not know the bank; this service does
        params["bank_account_last4"] = (await session.execute(select(members.c.bank_account_last4).where(
            members.c.subject == payload["recipient_subject"]))).scalar_one_or_none()
    title, body = render(payload["template"], payload["reference_id"], params)
    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    await session.execute(insert(notifications).values(
        event_id=event["event_id"], recipient_subject=payload["recipient_subject"],
        template=payload["template"], reference_id=payload["reference_id"], title=title, body=body
    ).on_conflict_do_nothing(index_elements=[notifications.c.event_id]))
