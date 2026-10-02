"""Every notification template renders with the parameters render() supplies (a missing placeholder would fail the
notification consumer and dead-letter the event, as NOMINATION_REGISTERED once did)."""
from string import Formatter

from app.domain.notifications import TEMPLATES, HI_TEMPLATES, render


def test_every_template_renders():
    for name in TEMPLATES:
        title, body = render(name, "REF-1", {"amount_paise": 12345600, "reason": "a reason", "bank_account_last4": "0001"})
        assert title and "{" not in body, name


def test_hindi_templates_cover_the_same_placeholders():
    assert HI_TEMPLATES.keys() == TEMPLATES.keys()
    fields = lambda value: {name for _, name, _, _ in Formatter().parse(value) if name}
    for name, (title, body) in TEMPLATES.items():
        hindi_title, hindi_body = HI_TEMPLATES[name]
        assert fields(title) == fields(hindi_title), name
        assert fields(body) == fields(hindi_body), name
        rendered_title, rendered_body = render(name, "REF-1", {"amount_paise": 12345600}, "hi")
        assert rendered_title and rendered_body and "{" not in rendered_body, name
