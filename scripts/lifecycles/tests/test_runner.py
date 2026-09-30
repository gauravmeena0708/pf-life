"""Isolation cleanup must happen on failure, and must never target the shared project."""
import sys

import pytest

from scripts import ui_manuals
from scripts.lifecycles import isolated_stack


def test_start_failure_stops_only_prepared_fixture(monkeypatch, tmp_path):
    fixture = tmp_path / "epfo-lifecycle-test"
    calls = []
    monkeypatch.setattr(sys, "argv", ["ui_manuals.py", "--isolated"])
    monkeypatch.setattr(isolated_stack, "prepare", lambda: fixture)
    monkeypatch.setattr(isolated_stack, "start", lambda folder: (_ for _ in ()).throw(RuntimeError("seed failed")))
    monkeypatch.setattr(isolated_stack, "run", lambda folder, *args: calls.append((folder, args)))
    with pytest.raises(RuntimeError, match="seed failed"):
        ui_manuals.main()
    assert calls == [(fixture, ("down",))]


def test_failed_ui_run_still_stops_isolation(monkeypatch, tmp_path):
    fixture = tmp_path / "epfo-lifecycle-test"
    calls = []
    monkeypatch.setattr(sys, "argv", ["ui_manuals.py", "--isolated", "--suite", "claims"])
    monkeypatch.setattr(isolated_stack, "prepare", lambda: fixture)
    monkeypatch.setattr(isolated_stack, "start", lambda folder: None)
    monkeypatch.setattr(isolated_stack, "run", lambda folder, *args: calls.append((folder, args)))
    def fail(args, output):
        assert args.base_url == "http://localhost:15173"
        return 1
    monkeypatch.setattr(ui_manuals, "capture_and_render", fail)
    assert ui_manuals.main() == 1
    assert calls == [(fixture, ("down",))]


def test_keep_stack_preserves_fixture(monkeypatch, tmp_path):
    fixture = tmp_path / "epfo-lifecycle-test"
    calls = []
    monkeypatch.setattr(sys, "argv", ["ui_manuals.py", "--isolated", "--keep-stack"])
    monkeypatch.setattr(isolated_stack, "prepare", lambda: fixture)
    monkeypatch.setattr(isolated_stack, "start", lambda folder: None)
    monkeypatch.setattr(isolated_stack, "run", lambda folder, *args: calls.append((folder, args)))
    monkeypatch.setattr(ui_manuals, "capture_and_render", lambda args, output: 0)
    assert ui_manuals.main() == 0
    assert calls == []
