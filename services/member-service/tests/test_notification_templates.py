"""Every notification template renders with the parameters render() supplies (a missing placeholder would fail the
notification consumer and dead-letter the event, as NOMINATION_REGISTERED once did)."""
from app.domain.notifications import TEMPLATES, render


def test_every_template_renders():
    for name in TEMPLATES:
        title, body = render(name, "REF-1", {"amount_paise": 12345600, "reason": "a reason", "bank_account_last4": "0001"})
        assert title and "{" not in body, name
