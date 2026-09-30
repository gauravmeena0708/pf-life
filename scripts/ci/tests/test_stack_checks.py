"""CI gates must include new database services and must not accept a silently skipped suite."""
import importlib.util
import urllib.error
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("stack_checks", Path(__file__).parents[1] / "stack_checks.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def test_new_database_service_is_migrated_without_a_hardcoded_list(tmp_path):
    folder = tmp_path / "services" / "new-service"
    folder.mkdir(parents=True)
    (folder / "alembic.ini").write_text("[alembic]\n")
    config = {"services": {"postgres": {}, "gateway": {"environment": {"REDIS_URL": "redis://redis"}},
                           "new-service": {"environment": {"DATABASE_URL": "postgresql://test"}}}}
    assert checks.migration_services(config, tmp_path) == ["new-service"]


def test_database_service_without_migrations_is_rejected(tmp_path):
    config = {"services": {"new-service": {"environment": {"DATABASE_URL": "postgresql://test"}}}}
    with pytest.raises(ValueError, match="no services/new-service/alembic.ini"):
        checks.migration_services(config, tmp_path)


def test_no_database_services_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="No database services"):
        checks.migration_services({"services": {"gateway": {}}}, tmp_path)


@pytest.mark.parametrize("report", [
    '<testsuites><testsuite tests="0"/></testsuites>',
    '<testsuites><testsuite tests="1"><testcase name="browser"><skipped/></testcase></testsuite></testsuites>',
    '<testsuites><testsuite tests="1"><testcase name="claim"><failure/></testcase></testsuite></testsuites>',
    '<testsuites><testsuite tests="1"><testcase name="claim"><error/></testcase></testsuite></testsuites>',
    '<testsuites><testsuite tests="2" skipped="1"><testcase name="claim"/></testsuite></testsuites>',
])
def test_empty_skipped_and_failed_reports_are_rejected(tmp_path, report):
    path = tmp_path / "results.xml"
    path.write_text(report)
    with pytest.raises(ValueError):
        checks.check_results(path)


def test_successful_report_is_accepted(tmp_path, capsys):
    path = tmp_path / "results.xml"
    path.write_text('<testsuites><testsuite tests="1"><testcase name="claim"/></testsuite></testsuites>')
    checks.check_results(path)
    assert "Verified 1 successful stack tests with no skips" in capsys.readouterr().out


def test_readiness_retries_a_realm_that_is_still_importing(monkeypatch, capsys):
    monkeypatch.setattr(checks, "ENTRY_POINTS", ("http://realm", "http://gateway"))
    clock = iter((0, 0, 1))
    monkeypatch.setattr(checks.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(checks.time, "sleep", lambda _: None)
    attempts = {}

    class Ready:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def open_url(url, timeout):
        attempts[url] = attempts.get(url, 0) + 1
        if url == "http://realm" and attempts[url] == 1:
            raise urllib.error.HTTPError(url, 503, "Realm not ready", {}, None)
        return Ready()

    monkeypatch.setattr(checks.urllib.request, "urlopen", open_url)
    checks.wait_for_entry_points(timeout=10)
    assert attempts == {"http://gateway": 1, "http://realm": 2}
    assert "Ready: http://realm" in capsys.readouterr().out


def test_readiness_timeout_fails_the_gate(monkeypatch):
    monkeypatch.setattr(checks, "ENTRY_POINTS", ("http://realm",))
    clock = iter((0, 1))
    monkeypatch.setattr(checks.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="did not become ready: http://realm"):
        checks.wait_for_entry_points(timeout=1)


@pytest.mark.parametrize("error", [ConnectionResetError(104, "Connection reset by peer"),
                                   ConnectionRefusedError(111, "Connection refused"),
                                   checks.http.client.RemoteDisconnected("closed")])
def test_readiness_retries_a_server_that_is_still_starting(monkeypatch, error):
    monkeypatch.setattr(checks, "ENTRY_POINTS", ("http://web",))
    clock = iter((0, 0, 1))
    monkeypatch.setattr(checks.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(checks.time, "sleep", lambda _: None)
    calls = []

    class Ready:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def open_url(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise error                       # what a freshly started Vite or gateway answers at first
        return Ready()

    monkeypatch.setattr(checks.urllib.request, "urlopen", open_url)
    checks.wait_for_entry_points(timeout=10)
    assert calls == ["http://web", "http://web"]
