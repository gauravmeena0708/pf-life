"""Startup retries stay bounded and never retry business submissions or UI assertions."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from playwright.sync_api import Error

from scripts.lifecycles.readiness import wait_for_sign_in


def fixture_browser(monkeypatch, failures):
    calls, contexts = [], []
    def goto(url):
        calls.append(url)
        if failures:
            error = failures.pop(0)
            if error:
                raise error
    def new_context():
        context = SimpleNamespace(closed=False)
        context.new_page = lambda: SimpleNamespace(
            set_default_timeout=lambda _: None, goto=goto,
            locator=lambda _: SimpleNamespace(fill=lambda _: None, click=lambda: None),
            get_by_role=lambda *args, **kwargs: None)
        context.close = lambda: setattr(context, 'closed', True)
        contexts.append(context)
        return context
    browser = SimpleNamespace(new_context=new_context, closed=False)
    browser.close = lambda: setattr(browser, 'closed', True)
    import playwright.sync_api as api
    monkeypatch.setattr(api, 'sync_playwright', lambda: nullcontext(SimpleNamespace(chromium=SimpleNamespace(launch=lambda: browser))))
    monkeypatch.setattr(api, 'expect', lambda _: SimpleNamespace(to_have_url=lambda *args, **kwargs: None, to_be_visible=lambda **kwargs: None))
    monkeypatch.setattr('scripts.lifecycles.readiness.time.sleep', lambda _: None)
    return calls, contexts, browser


def test_transport_retry_only_authentication_and_close_every_context(monkeypatch):
    calls, contexts, browser = fixture_browser(monkeypatch, [Error('net::ERR_CONNECTION_RESET'), None])
    wait_for_sign_in('http://localhost:15173')
    assert calls == ['http://localhost:15173/auth/login?persona=member-a&return_to=/member/passbook'] * 2
    assert all(context.closed for context in contexts) and browser.closed


@pytest.mark.parametrize('failure', [AssertionError('Wrong member landing page'), Error('Invalid sign-in configuration')])
def test_assertions_and_non_transport_errors_are_not_retried(monkeypatch, failure):
    calls, contexts, browser = fixture_browser(monkeypatch, [failure])
    with pytest.raises(type(failure)):
        wait_for_sign_in('http://localhost:15173')
    assert len(calls) == 1
    assert all(context.closed for context in contexts) and browser.closed


def test_transport_retry_limit_propagates_error_and_closes_browser(monkeypatch):
    calls, contexts, browser = fixture_browser(monkeypatch, [Error('net::ERR_CONNECTION_REFUSED')] * 4)
    with pytest.raises(Error, match='CONNECTION_REFUSED'):
        wait_for_sign_in('http://localhost:15173', attempts=4)
    assert len(calls) == 4
    assert all(context.closed for context in contexts) and browser.closed
