"""No manufactured lifecycle passes; both test results and complete, untampered evidence are needed."""
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.lifecycles.catalogue import validate_catalogue
from scripts.lifecycles.report import evidence_status, write_report
from scripts.manuals.recording import DISCLAIMER
from scripts.manuals.render import build_manuals


@pytest.fixture
def lifecycle(tmp_path):
    folder = tmp_path / "evidence" / "case"
    folder.mkdir(parents=True)
    Image.new("RGB", (32, 24), "white").save(folder / "01.png")
    manifest = {"schema_version": 1, "scenario": "case", "title": "Lifecycle", "status": "passed",
                "purpose": "Follow roles", "scope": "One complete synthetic case", "prerequisites": ["Baseline"],
                "limitations": ["Mock bank"], "disclaimer": DISCLAIMER, "finished_at": "2026-09-30T12:00:00Z",
                "checkout": {"commit": "test", "dirty": True},
                "lifecycle": {"case_ids": ["CLM-SETTLE-REVIEW"], "data": "Synthetic input", "expected_outcome": "SETTLED",
                              "outcome": "SETTLED", "observations": [{"stage": "Outcome", "value": "SETTLED", "step": 1}]},
                "steps": [{"role": "Member", "number": 1, "title": "Settlement", "instruction": "Track.", "expected": "Settled.",
                           "url": "http://localhost/member/claims/CLM-DEMO", "captured_at": "2026-09-30T12:00:00Z", "screenshot": "01.png",
                           "sha256": hashlib.sha256((folder / "01.png").read_bytes()).hexdigest()}]}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.xml").write_text('<testsuites><testsuite><testcase name="claim"><properties>'
                                       '<property name="lifecycle_cases" value="CLM-SETTLE-REVIEW"/></properties></testcase></testsuite></testsuites>')
    return tmp_path, folder, manifest


def save(folder, manifest):
    (folder / "manifest.json").write_text(json.dumps(manifest))


def test_inventory_has_unique_ids_and_real_references():
    cases = validate_catalogue()
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert {case["family"] for case in cases} >= {"Claims", "Pension", "Mobility", "Contributions"}


def test_offline_inventory_never_claims_live_verification(tmp_path):
    index = write_report(tmp_path)
    coverage = json.loads(index.with_name("coverage.json").read_text())
    assert coverage["status_counts"] == {"not_run": len(coverage["cases"])}
    assert "No UI evidence" in index.read_text()


def test_pass_needs_junit_and_valid_evidence(lifecycle):
    output, _, _ = lifecycle
    assert evidence_status(output)["CLM-SETTLE-REVIEW"]["status"] == "ui_passed"
    (output / "results.xml").unlink()
    assert evidence_status(output)["CLM-SETTLE-REVIEW"]["status"] == "evidence_invalid"


@pytest.mark.parametrize("fault", ["outcome", "image", "escape", "disclaimer", "steps"])
def test_invalid_evidence_is_not_verified(lifecycle, fault):
    output, folder, manifest = lifecycle
    if fault == "outcome": manifest["lifecycle"]["outcome"] = "PAYMENT_PENDING"
    if fault == "image": (folder / "01.png").write_bytes(b"changed")
    if fault == "escape": manifest["steps"][0]["screenshot"] = "../01.png"
    if fault == "disclaimer": manifest["disclaimer"] = "Official EPFO"
    if fault == "steps": manifest["steps"] = []
    save(folder, manifest)
    assert evidence_status(output)["CLM-SETTLE-REVIEW"]["status"] == "evidence_invalid"


def test_failed_junit_prevents_pass_despite_passed_manifest(lifecycle):
    output, _, _ = lifecycle
    xml = (output / "results.xml").read_text().replace("</testcase>", '<failure message="fixture failed"/></testcase>')
    (output / "results.xml").write_text(xml)
    assert evidence_status(output)["CLM-SETTLE-REVIEW"]["status"] == "failed"


def test_process_manual_follows_roles_in_execution_order(lifecycle):
    output, folder, manifest = lifecycle
    original = manifest["steps"][0]
    manifest["steps"] += [{**original, "role": "Cash section", "number": 2, "title": "Cash action"},
                          {**original, "number": 3, "title": "Member final check"}]
    save(folder, manifest)
    index = build_manuals(output, pdf=False)
    catalogue = json.loads(index.with_name("catalogue.json").read_text())
    process = next(entry for entry in catalogue["manuals"] if entry["kind"] == "process")
    text = (index.parent / (process["name"] + ".html")).read_text()
    assert text.index("1. Settlement") < text.index("2. Cash action") < text.index("3. Member final check")
    assert "Asserted outcome" in text and "SETTLED" in text
    assert process["steps"] == 3


def test_process_manual_refuses_missing_terminal_outcome(lifecycle):
    output, folder, manifest = lifecycle
    del manifest["lifecycle"]["outcome"]
    save(folder, manifest)
    with pytest.raises(ValueError, match="asserted outcome"):
        build_manuals(output, pdf=False)


def test_report_links_existing_run_in_another_directory(lifecycle, tmp_path):
    output, _, _ = lifecycle
    build_manuals(output, pdf=False)
    index = write_report(tmp_path / "separate-report", output)
    text = index.read_text()
    assert "../../evidence/case/manifest.json" in text
    assert "../../manuals/case-cross-role-process.html" in text
