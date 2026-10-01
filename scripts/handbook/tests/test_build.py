"""Publication must never turn incomplete or altered captures into a verified replay."""
import base64
import hashlib
import json

import pytest

from scripts.handbook.build import json_script, load_replays, recorded_cases
from scripts.manuals.recording import DISCLAIMER


@pytest.fixture
def capture(tmp_path):
    folder = tmp_path / "evidence" / "sample"
    folder.mkdir(parents=True)
    raw = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=")
    (folder / "01.png").write_bytes(raw)
    (tmp_path / "results.xml").write_text('<testsuite><testcase name="sample"><properties><property name="lifecycle_cases" value="CLM-SETTLE-REVIEW"/></properties></testcase></testsuite>')
    manifest = {
        "schema_version": 1, "scenario": "sample", "status": "passed", "disclaimer": DISCLAIMER,
        "finished_at": "2026-09-30T09:00:00Z",
        "lifecycle": {"case_ids": ["CLM-SETTLE-REVIEW"], "expected_outcome": "SETTLED", "outcome": "SETTLED",
                      "observations": [{"step": 1, "stage": "Outcome", "value": "SETTLED"}]},
        "steps": [{"number": 1, "role": "Member", "title": "Observe outcome", "instruction": "Read status", "expected": "Settled",
                   "captured_at": "2026-09-30T09:00:00Z", "screenshot": "01.png", "sha256": hashlib.sha256(raw).hexdigest()}],
    }
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest))
    return tmp_path, path, manifest, [{"scenario": "sample", "title": "Sample", "lesson": "Test", "anchors": [1]}]


def save(path, manifest):
    path.write_text(json.dumps(manifest))


def test_replay_embeds_original_bytes_and_original_step_number(capture):
    run, path, _, definitions = capture
    replay = load_replays(run, definitions)[0][0]
    assert replay["steps"][0]["number"] == 1
    embedded = base64.b64decode(replay["steps"][0]["image"].split(",", 1)[1])
    assert embedded == (path.parent / "01.png").read_bytes()
    assert replay["manifest_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("kind", ["failed_test", "missing_test", "failed_manifest", "wrong_outcome", "changed_image", "escape_path", "unknown_case"])
def test_unverified_evidence_cannot_publish(capture, kind):
    run, path, manifest, definitions = capture
    if kind == "failed_test":
        text = (run / "results.xml").read_text().replace('</testcase>', '<failure message="assertion failed"/></testcase>')
        (run / "results.xml").write_text(text)
    elif kind == "missing_test":
        (run / "results.xml").unlink()
    elif kind == "failed_manifest":
        manifest["status"] = "failed"
    elif kind == "wrong_outcome":
        manifest["lifecycle"]["outcome"] = "APPROVED"
    elif kind == "changed_image":
        (path.parent / "01.png").write_bytes(b"changed")
    elif kind == "escape_path":
        manifest["steps"][0]["screenshot"] = "../01.png"
    elif kind == "unknown_case":
        manifest["lifecycle"]["case_ids"] = ["MADE-UP"]
    save(path, manifest)
    with pytest.raises(ValueError):
        load_replays(run, definitions)


def test_observation_requires_recorded_step(capture):
    run, path, manifest, definitions = capture
    manifest["lifecycle"]["observations"][0]["step"] = 99
    save(path, manifest)
    with pytest.raises(ValueError, match="absent evidence step"):
        load_replays(run, definitions)


def test_pdf_anchor_requires_selected_business_capture(capture):
    run, _, _, definitions = capture
    definitions[0]["anchors"] = [99]
    with pytest.raises(ValueError, match="Missing PDF anchor"):
        load_replays(run, definitions)


def test_duplicate_step_numbers_cannot_publish(capture):
    run, path, manifest, definitions = capture
    manifest["steps"].append(dict(manifest["steps"][0]))
    save(path, manifest)
    with pytest.raises(ValueError, match="duplicate evidence step"):
        load_replays(run, definitions)


def test_imported_text_cannot_close_inline_data_script():
    encoded = json_script({"title": '</script><script>alert("x")</script>'})
    assert "</script>" not in encoded
    assert json.loads(encoded)["title"].startswith("</script>")


def test_editorial_amount_must_match_recorded_partition(capture):
    run, _, _, definitions = capture
    definitions[0]["expected_fields"] = {"amount_paise": 4650000}
    with pytest.raises(ValueError, match="Editorial example needs review"):
        load_replays(run, definitions)


def test_coverage_denominator_is_the_recording_snapshot(capture):
    run, _, _, definitions = capture
    (run / "lifecycles").mkdir()
    snapshot = {"schema_version": 1, "disclaimer": DISCLAIMER, "cases": [
        {"case_id": "CLM-SETTLE-REVIEW", "status": "ui_passed"},
        {"case_id": "CLM-SETTLE-F19", "status": "not_run"}]}
    (run / "lifecycles/coverage.json").write_text(json.dumps(snapshot))
    _, statuses = load_replays(run, definitions)
    assert len(recorded_cases(run, statuses)) == 2
    # The snapshot cannot claim a pass that lacks verified recorded evidence.
    snapshot["cases"][1]["status"] = "ui_passed"
    (run / "lifecycles/coverage.json").write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match="disagrees with validated evidence"):
        recorded_cases(run, statuses)
