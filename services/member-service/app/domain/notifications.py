"""Plain-language notices for synthetic claim events."""
from typing import Any
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import hashlib
import hmac

import httpx

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infra.tables import (members, employments, notifications, notification_preferences,
                              notification_deliveries, notification_delivery_attempts)
from epfo_persistence import add_event
from epfo_persistence.policy import rules_on, section

TEMPLATES = {
    "CLAIM_SUBMITTED": ("Claim submitted", "Your claim {reference_id} was submitted. We will tell you when it moves forward."),
    "CLAIM_UNDER_REVIEW": ("Claim under review", "Your claim {reference_id} is being reviewed."),
    "CLAIM_APPROVED": ("Claim approved", "Your claim {reference_id}{amount} was approved. Payment is being arranged."),
    "CLAIM_REJECTED": ("Claim rejected", "Your claim {reference_id} was rejected. {reason}"),
    "CLAIM_SETTLED": ("Claim paid", "Your claim {reference_id}{amount} was paid into your bank account{bank_ending}.{tax_note}"),
    "CLAIM_PAYMENT_RETURNED": ("Claim payment returned", "The payment for your claim {reference_id} was returned by the bank. {reason}"),
    "CLAIM_REISSUED": ("Claim payment reissued", "Payment for your claim {reference_id} was reissued."),
    "GRIEVANCE_REGISTERED": ("Grievance registered", "Your grievance {reference_id} was registered and sent to your regional office."),
    "GRIEVANCE_REPLY": ("Reply to your grievance", "There is a new reply on your grievance {reference_id}."),
    "GRIEVANCE_ESCALATED": ("Grievance escalated", "Your grievance {reference_id} was escalated to the next level."),
    "GRIEVANCE_RESOLVED": ("Grievance resolved", "Your grievance {reference_id} was resolved. You can reopen it within 30 days if the problem remains."),
    "CONTACT_DETAILS_CHANGED": ("Contact details changed", "Your mobile number and email were changed. If this was not you, report it and ask for account recovery straight away."),
    "ACCOUNT_RECOVERY_APPROVED": ("Account recovered", "Your account recovery {reference_id} was approved and your verified contact details were restored."),
    "JD_EMPLOYER_ATTESTED": ("Correction request attested", "Your employer confirmed your {parameter} correction ({reference_id}); your regional office will now check it."),
    "JD_RETURNED_BY_EMPLOYER": ("Correction request returned", "Your employer returned your {parameter} correction ({reference_id}): {reason} You can file it again."),
    "JD_REJECTED_BY_EMPLOYER": ("Correction request not supported", "Your employer did not support your {parameter} correction ({reference_id}): {reason}"),
    "JD_APPROVED": ("Profile corrected", "Your {parameter} was corrected ({reference_id}). It now shows on your profile."),
    "JD_REJECTED": ("Correction request rejected", "Your {parameter} correction ({reference_id}) was rejected: {reason}"),
    "INTEREST_CREDITED": ("Interest credited", "Interest{amount} for {financial_year} at {rate} was credited to your PF account {reference_id}."),
    "INTEREST_REVISED": ("Interest revised", "The interest rate for {financial_year} was revised to {rate}; the difference{amount} was adjusted in your PF account {reference_id}."),
    "EXIT_RECORDED": ("Date of exit recorded", "The date of exit {date_of_exit} was recorded for your member ID {reference_id} (marked by the {marked_by})."),
    "NOMINATION_REGISTERED": ("e-Nomination registered", "Your e-nomination {reference_id} was signed and registered; it replaces any earlier nomination."),
    "HIGHER_PENSION_VALIDATED": ("Higher pension option validated", "Your employer validated your option {reference_id}; dues were worked out{amount}. The office decides next."),
    "HIGHER_PENSION_REJECTED_BY_EMPLOYER": ("Higher pension option not validated", "Your employer did not validate your option {reference_id}: {reason}"),
    "OFFICE_NOTICE": ("Notice from EPFO", "{reason} (reference {reference_id})"),
    "EXIT_CORRECTED": ("Date of exit corrected", "Your employer corrected the date of exit of your member ID {reference_id} to {date_of_exit}."),
    "TRANSFER_POSTED": ("Transfer completed", "Your PF balance{amount} was transferred from member ID {from_id} to {to_id} ({reference_id}). You can download Annexure K."),
    "KYC_APPROVED": ("KYC approved", "Your employer approved your {parameter} KYC ({reference_id}). It now shows as verified."),
    "KYC_REJECTED": ("KYC not approved", "Your employer did not approve your {parameter} KYC ({reference_id}): {reason}"),
    "ACCOUNT_RECOVERY_REJECTED": ("Account recovery not approved", "Your account recovery request {reference_id} was not approved. Please contact your regional office."),
    "AUTO_TRANSFER_STARTED": ("Your earlier PF is moving to your new member ID", "The balance of your earlier member ID{amount} is being moved to your current one ({reference_id}). You need not do anything."),
}

HI_TEMPLATES = {
    "CLAIM_SUBMITTED": ("दावा प्रस्तुत किया गया", "आपका दावा {reference_id} प्रस्तुत कर दिया गया है। आगे की प्रगति की सूचना दी जाएगी।"),
    "CLAIM_UNDER_REVIEW": ("दावे की जाँच जारी है", "आपके दावे {reference_id} की जाँच की जा रही है।"),
    "CLAIM_APPROVED": ("दावा स्वीकृत", "आपका दावा {reference_id}{amount} स्वीकृत हो गया है। भुगतान की व्यवस्था की जा रही है।"),
    "CLAIM_REJECTED": ("दावा अस्वीकृत", "आपका दावा {reference_id} अस्वीकृत कर दिया गया है। {reason}"),
    "CLAIM_SETTLED": ("दावे का भुगतान", "आपके दावे {reference_id}{amount} का भुगतान आपके बैंक खाते{bank_ending} में कर दिया गया है।{tax_note}"),
    "CLAIM_PAYMENT_RETURNED": ("दावे का भुगतान वापस आया", "आपके दावे {reference_id} का भुगतान बैंक से वापस आ गया है। {reason}"),
    "CLAIM_REISSUED": ("दावे का भुगतान पुनः जारी", "आपके दावे {reference_id} का भुगतान पुनः जारी किया गया है।"),
    "GRIEVANCE_REGISTERED": ("शिकायत दर्ज", "आपकी शिकायत {reference_id} दर्ज कर क्षेत्रीय कार्यालय को भेज दी गई है।"),
    "GRIEVANCE_REPLY": ("शिकायत पर उत्तर", "आपकी शिकायत {reference_id} पर नया उत्तर प्राप्त हुआ है।"),
    "GRIEVANCE_ESCALATED": ("शिकायत आगे भेजी गई", "आपकी शिकायत {reference_id} अगले स्तर पर भेज दी गई है।"),
    "GRIEVANCE_RESOLVED": ("शिकायत का निवारण", "आपकी शिकायत {reference_id} का निवारण हो गया है। समस्या बनी रहने पर आप 30 दिनों के भीतर इसे पुनः खोल सकते हैं।"),
    "CONTACT_DETAILS_CHANGED": ("संपर्क विवरण बदला गया", "आपका मोबाइल नंबर और ईमेल बदले गए हैं। यदि आपने ऐसा नहीं किया है, तो तुरंत सूचना देकर खाता पुनर्प्राप्ति का अनुरोध करें।"),
    "ACCOUNT_RECOVERY_APPROVED": ("खाता पुनर्प्राप्त", "आपका खाता पुनर्प्राप्ति अनुरोध {reference_id} स्वीकृत हुआ और सत्यापित संपर्क विवरण बहाल कर दिए गए हैं।"),
    "JD_EMPLOYER_ATTESTED": ("सुधार अनुरोध सत्यापित", "आपके नियोक्ता ने {parameter} सुधार ({reference_id}) की पुष्टि की है; अब क्षेत्रीय कार्यालय इसकी जाँच करेगा।"),
    "JD_RETURNED_BY_EMPLOYER": ("सुधार अनुरोध वापस", "आपके नियोक्ता ने {parameter} सुधार ({reference_id}) वापस किया है: {reason} आप पुनः आवेदन कर सकते हैं।"),
    "JD_REJECTED_BY_EMPLOYER": ("सुधार अनुरोध समर्थित नहीं", "आपके नियोक्ता ने {parameter} सुधार ({reference_id}) का समर्थन नहीं किया है: {reason}"),
    "JD_APPROVED": ("प्रोफ़ाइल में सुधार", "आपका {parameter} सुधार ({reference_id}) पूरा हो गया है। यह अब आपकी प्रोफ़ाइल में दिखाई देता है।"),
    "JD_REJECTED": ("सुधार अनुरोध अस्वीकृत", "आपका {parameter} सुधार ({reference_id}) अस्वीकृत हुआ: {reason}"),
    "INTEREST_CREDITED": ("ब्याज जमा", "वित्त वर्ष {financial_year} के लिए {rate} की दर से ब्याज{amount} आपके पीएफ खाते {reference_id} में जमा हुआ है।"),
    "INTEREST_REVISED": ("ब्याज संशोधित", "वित्त वर्ष {financial_year} की ब्याज दर {rate} की गई है; अंतर{amount} आपके पीएफ खाते {reference_id} में समायोजित हुआ है।"),
    "EXIT_RECORDED": ("सेवा समाप्ति तिथि दर्ज", "आपके सदस्य आईडी {reference_id} की सेवा समाप्ति तिथि {date_of_exit} दर्ज हुई है (दर्जकर्ता: {marked_by})।"),
    "NOMINATION_REGISTERED": ("ई-नामांकन दर्ज", "आपका ई-नामांकन {reference_id} हस्ताक्षरित होकर दर्ज हो गया है; यह पिछले नामांकन का स्थान लेता है।"),
    "HIGHER_PENSION_VALIDATED": ("उच्च पेंशन विकल्प सत्यापित", "आपके नियोक्ता ने विकल्प {reference_id} सत्यापित किया है; देय राशि{amount} तय की गई है। आगे कार्यालय निर्णय करेगा।"),
    "HIGHER_PENSION_REJECTED_BY_EMPLOYER": ("उच्च पेंशन विकल्प सत्यापित नहीं", "आपके नियोक्ता ने विकल्प {reference_id} सत्यापित नहीं किया है: {reason}"),
    "OFFICE_NOTICE": ("ईपीएफओ से सूचना", "{reason} (संदर्भ {reference_id})"),
    "EXIT_CORRECTED": ("सेवा समाप्ति तिथि सुधारी गई", "आपके नियोक्ता ने सदस्य आईडी {reference_id} की सेवा समाप्ति तिथि {date_of_exit} कर दी है।"),
    "TRANSFER_POSTED": ("अंतरण पूरा", "आपकी पीएफ शेष राशि{amount} सदस्य आईडी {from_id} से {to_id} में अंतरित हुई है ({reference_id})। आप अनुलग्नक के डाउनलोड कर सकते हैं।"),
    "KYC_APPROVED": ("केवाईसी स्वीकृत", "आपके नियोक्ता ने {parameter} केवाईसी ({reference_id}) स्वीकृत किया है। अब यह सत्यापित दिखता है।"),
    "KYC_REJECTED": ("केवाईसी स्वीकृत नहीं", "आपके नियोक्ता ने {parameter} केवाईसी ({reference_id}) स्वीकृत नहीं किया है: {reason}"),
    "ACCOUNT_RECOVERY_REJECTED": ("खाता पुनर्प्राप्ति अस्वीकृत", "आपका खाता पुनर्प्राप्ति अनुरोध {reference_id} स्वीकृत नहीं हुआ है। कृपया क्षेत्रीय कार्यालय से संपर्क करें।"),
    "AUTO_TRANSFER_STARTED": ("आपका पुराना पीएफ नई सदस्य आईडी में जा रहा है", "आपकी पिछली सदस्य आईडी की राशि{amount} आपकी वर्तमान सदस्य आईडी में भेजी जा रही है ({reference_id})। आपको कुछ नहीं करना है।"),
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


def render(template: str, reference_id: str, params: dict[str, Any] | None = None,
           language: str = "en") -> tuple[str, str]:
    title, body = (HI_TEMPLATES if language == "hi" else TEMPLATES).get(
        template, ("सूचना", "संदर्भ {reference_id} के बारे में नई सूचना है।") if language == "hi"
        else ("Update", "There is an update about {reference_id}."))
    values = params or {}
    ending = values.get("bank_account_last4")
    reason = str(values.get("reason") or "Check your claim details for more information.")
    paise = values.get("amount_paise")
    amount = f" for {rupees(abs(int(paise)))}" if paise is not None else ""
    tds = values.get("tds_paise")
    return title, body.format(reference_id=reference_id, reason=reason, parameter=values.get("parameter") or "profile",
                              amount=amount, bank_ending=f" ending {ending}" if ending else "",
                              tax_note=f" Income tax of {rupees(int(tds))} was deducted at source (TDS)." if tds else "",
                              financial_year=values.get("financial_year") or "", rate=values.get("rate") or "",
                              date_of_exit=values.get("date_of_exit") or "", marked_by=values.get("marked_by") or "employer",
                              from_id=values.get("from") or "", to_id=values.get("to") or "")


async def handle_notification_requested(session: AsyncSession, event: dict[str, Any]) -> None:
    if (await session.execute(select(notifications.c.id).where(
            notifications.c.event_id == event["event_id"]))).first():
        return
    payload = event["payload"]
    if not payload.get("recipient_subject"):         # a member without a login has no inbox (nor channel preferences)
        return
    params = dict(payload.get("params") or {})
    member = (await session.execute(select(members).where(
        members.c.subject == payload["recipient_subject"]))).mappings().first()
    if not member:
        return
    if "bank_account_last4" not in params:
        params["bank_account_last4"] = member["bank_account_last4"]
    prefs = (await session.execute(select(notification_preferences).where(
        notification_preferences.c.subject == payload["recipient_subject"]))).mappings().first()
    rules = section(await rules_on(session, datetime.now(UTC).date()), "notifications")
    language = prefs["language"] if prefs else "en"
    title, body = render(payload["template"], payload["reference_id"], params, language)
    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    result = await session.execute(insert(notifications).values(
        event_id=event["event_id"], recipient_subject=payload["recipient_subject"],
        template=payload["template"], reference_id=payload["reference_id"], title=title, body=body
    ).on_conflict_do_nothing(index_elements=[notifications.c.event_id]).returning(notifications.c.id))
    notification_id = result.scalar_one_or_none()
    if notification_id is None:
        return
    office_id = (await session.execute(select(employments.c.office_id).where(
        employments.c.member_id == member["member_id"]).order_by(
        employments.c.date_of_joining.desc()).limit(1))).scalar_one_or_none()
    now = datetime.now(UTC)
    sms_on = (prefs is None or prefs["sms"] or payload["template"] in rules["essential_templates"])
    email_on = prefs is None or prefs["email"]
    sms = "EPFO: " + title + ". " + body
    limit = int(rules["sms_max_chars"])
    if len(sms) > limit:
        sms = sms[:limit - 1] + "…"
    for channel, enabled, destination, content, subject, reason in (
        ("SMS", sms_on, member["mobile_masked"], sms, None, "Member turned SMS off"),
        ("EMAIL", email_on, member["email_masked"], body + "\n\nEPFO member portal (synthetic demonstration).", title,
         "Member turned email off"),
    ):
        await session.execute(notification_deliveries.insert().values(
            delivery_id=str(uuid4()), notification_id=notification_id, recipient_subject=payload["recipient_subject"],
            office_id=office_id, channel=channel, destination_masked=destination, language=language,
            text=content, subject=subject, state="QUEUED" if enabled else "SKIPPED",
            reason=None if enabled else reason, attempts=0, next_attempt_at=now if enabled else None,
            sender_id=rules["sender_id"] if channel == "SMS" else None, created_at=now, updated_at=now))


async def gateway_transport(channel: str, payload: dict) -> httpx.Response:
    path = "/mock-sms/messages" if channel == "SMS" else "/mock-email/messages"
    signature = hmac.new(settings.mock_gateway_secret.encode(), path.encode(), hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(timeout=3) as client:
        return await client.post(settings.mock_integrations_url.rstrip("/") + path, json=payload,
                                 headers={"X-Signature": signature})


async def deliver_due(session: AsyncSession, now: datetime, transport=gateway_transport) -> None:
    rules = section(await rules_on(session, now.date()), "notifications")
    rows = (await session.execute(select(notification_deliveries, notifications.c.template, notifications.c.reference_id)
        .join(notifications, notifications.c.id == notification_deliveries.c.notification_id)
        .where(notification_deliveries.c.state.in_(["QUEUED", "RETRYING"]),
               notification_deliveries.c.next_attempt_at <= now)
        .order_by(notification_deliveries.c.created_at, notification_deliveries.c.delivery_id)
        .with_for_update(of=notification_deliveries, skip_locked=True))).mappings().all()
    for row in rows:
        attempt = row["attempts"] + 1
        payload = ({"to": row["destination_masked"], "sender_id": row["sender_id"],
                    "template_key": row["template"], "text": row["text"], "reference": row["reference_id"]}
                   if row["channel"] == "SMS" else
                   {"to": row["destination_masked"], "subject": row["subject"], "body": row["text"],
                    "reference": row["reference_id"]})
        status = None
        message_id = None
        error = None
        gateway_status = None
        try:
            response = await transport(row["channel"], payload)
            status = response.status_code
            data = response.json()
            message_id = data.get("message_id")
            gateway_status = data.get("status") or data.get("title")
        except (httpx.RequestError, OSError, ValueError) as exc:
            error = str(exc)[:300]
        if status is not None and 200 <= status < 300:
            state, reason, next_at = "DELIVERED", None, None
        elif status is not None and 400 <= status < 500:
            state, reason, next_at = "FAILED", str(gateway_status or f"HTTP {status}")[:300], None
        elif attempt % int(rules["max_attempts"]) == 0:
            state, reason, next_at = "FAILED", f"gateway unavailable after {rules['max_attempts']} attempts", None
        else:
            delays = rules["retry_minutes"]
            state, reason = "RETRYING", None
            next_at = now + timedelta(minutes=delays[min((attempt - 1) % int(rules["max_attempts"]), len(delays) - 1)])
        await session.execute(notification_delivery_attempts.insert().values(
            delivery_id=row["delivery_id"], attempt=attempt, at=now, outcome=state,
            http_status=status, gateway_message_id=message_id, error=error or reason))
        await session.execute(update(notification_deliveries).where(
            notification_deliveries.c.delivery_id == row["delivery_id"],
            notification_deliveries.c.state.in_(["QUEUED", "RETRYING"])).values(
            state=state, reason=reason, attempts=attempt, next_attempt_at=next_at,
            gateway_message_id=message_id, last_error=error or reason, updated_at=now))
        if state == "FAILED":
            await add_event(session, producer="member-service", event_type="NotificationDeliveryFailed.v1",
                            aggregate_type="notification_delivery", aggregate_id=row["delivery_id"],
                            payload={"delivery_id": row["delivery_id"], "channel": row["channel"],
                                     "template": row["template"], "attempts": attempt, "reason": reason})
