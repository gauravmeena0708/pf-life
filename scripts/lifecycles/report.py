"""Report specifications separately from verified UI evidence; never infer a pass from test code."""
import csv
import hashlib
import html
import json
import os
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.lifecycles.catalogue import BY_ID, validate_catalogue
from scripts.manuals.recording import DISCLAIMER, now
from scripts.manuals.render import slug


def evidence_status(output: Path | None):
    if output is None:
        return {}
    junit = output / "results.xml"
    results = {}
    if junit.exists():
        for test in ET.parse(junit).getroot().iter("testcase"):
            for prop in test.findall("properties/property"):
                if prop.get("name") == "lifecycle_cases":
                    key = frozenset(prop.get("value", "").split(","))
                    status = "failed" if test.find("failure") is not None or test.find("error") is not None else "skipped" if test.find("skipped") is not None else "ui_passed"
                    # Multiple attempts for the same cases must not hide a failure.
                    if results.get(key) != "failed":
                        results[key] = status
    observed = {}
    for path in sorted((output / "evidence").glob("*/manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        lifecycle = manifest.get("lifecycle")
        if not lifecycle:
            continue
        ids = lifecycle["case_ids"]
        if not ids or any(case_id not in BY_ID for case_id in ids):
            raise ValueError(f"Unknown lifecycle case IDs in {path}")
        status = results.get(frozenset(ids), "evidence_invalid")
        if manifest.get("status") != "passed":
            status = "failed"
        if status == "ui_passed":
            try:
                if (manifest.get("schema_version") != 1 or manifest.get("disclaimer") != DISCLAIMER
                        or not manifest.get("steps") or not lifecycle.get("observations")
                        or not lifecycle.get("expected_outcome") or lifecycle.get("outcome") != lifecycle["expected_outcome"]):
                    raise ValueError("Incomplete lifecycle outcome")
                for step in manifest["steps"]:
                    image = (path.parent / step["screenshot"]).resolve()
                    if image.parent != path.parent.resolve() or image.suffix != ".png":
                        raise ValueError("Evidence outside scenario folder")
                    if hashlib.sha256(image.read_bytes()).hexdigest() != step["sha256"]:
                        raise ValueError("Changed evidence")
            except (ValueError, OSError, KeyError):
                status = "evidence_invalid"
        for case_id in ids:
            entry = {"status": status, "scenario": manifest["scenario"], "outcome": lifecycle.get("outcome", "Not reached"),
                     "manifest": str(path.relative_to(output)),
                     "process_manual": f"manuals/{slug(manifest['scenario'] + '-Cross-role process')}.html"}
            if observed.get(case_id, {}).get("status") not in {"failed", "evidence_invalid"}:
                observed[case_id] = entry
    return observed


def write_report(output: Path, run: Path | None = None) -> Path:
    cases = validate_catalogue()
    observed = evidence_status(run)
    rows = [{**case, **observed.get(case["case_id"], {"status": "not_run", "outcome": "Not observed in this run"})} for case in cases]
    folder = output / "lifecycles"
    folder.mkdir(parents=True, exist_ok=False)
    counts = dict(Counter(row["status"] for row in rows))
    payload = {"schema_version": 1, "generated_at": now(), "disclaimer": DISCLAIMER,
               "scope": "Finite baseline POC case inventory; not exhaustive for real EPFO or arbitrary policy extensions",
               "status_counts": counts, "cases": rows}
    (folder / "coverage.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = ["case_id", "family", "category", "title", "data", "prerequisite", "expected", "integration", "reference", "status", "outcome"]
    with (folder / "coverage.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    esc = html.escape
    family_options = ''.join(f'<option>{esc(family)}</option>' for family in dict.fromkeys(row['family'] for row in rows))
    table_rows = []
    for row in rows:
        evidence = "No UI evidence in this run"
        if row.get("manifest"):
            evidence_path = Path(os.path.relpath(run / row["manifest"], folder)).as_posix()
            evidence = f'<a href="{esc(evidence_path)}">Evidence manifest</a>'
            if row["status"] == "ui_passed" and (run / row["process_manual"]).is_file():
                manual_path = Path(os.path.relpath(run / row["process_manual"], folder)).as_posix()
                evidence += f' · <a href="{esc(manual_path)}">Process manual</a>'
        table_rows.append(f'<tr data-family="{esc(row["family"])}" data-status="{row["status"]}">'
                          f'<th scope="row"><code>{row["case_id"]}</code><br>{esc(row["title"])}</th>'
                          f'<td>{esc(row["family"])}<br><small>{esc(row["category"])}</small></td>'
                          f'<td>{esc(row["data"])}<p class="muted">Requires: {esc(row["prerequisite"])}</p></td>'
                          f'<td>{esc(row["expected"])}<p class="muted">{esc(row["integration"])}</p></td>'
                          f'<td><strong class="status {row["status"]}">{row["status"].replace("_", " ")}</strong><p>{esc(row["outcome"])}</p>{evidence}'
                          f'<details><summary>Supporting code / test definition</summary><code>{esc(row["reference"])}</code>'
                          '<p>A reference does not establish a passing test result or complete coverage of this case.</p></details></td></tr>')
    css = Path(__file__).with_name("report.css").read_text(encoding="utf-8")
    status_options = ''.join(f'<option value="{s}">{s.replace("_", " ")}</option>' for s in ["ui_passed", "failed", "skipped", "evidence_invalid", "not_run"])
    content = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PF Life · Lifecycle coverage</title><style>{css}</style></head><body>
<header><p>PF LIFE · PROCESS ASSURANCE</p><h1>Lifecycle cases and evidence</h1><p>Follow the record, the role handoffs and the business outcome.</p></header>
<main><p class="notice">{esc(DISCLAIMER)}</p><section class="summary" aria-label="Coverage summary">
<div><strong>{len(rows)}</strong><span>Specified cases</span></div><div><strong>{counts.get('ui_passed', 0)}</strong><span>Verified through UI</span></div>
<div><strong>{sum(counts.get(s, 0) for s in ['failed', 'evidence_invalid'])}</strong><span>Failed / invalid evidence</span></div>
<div><strong>{counts.get('not_run', 0)}</strong><span>Not run</span></div></section>
<p>A passing case means its asserted observations passed in this run. It does not prove every data combination, every branch of its process, or a live bank integration. Supporting code and test definitions remain distinct from observed results.</p>
<p><a href="coverage.csv">Download case matrix (CSV)</a> · <a href="coverage.json">Machine-readable coverage (JSON)</a></p>
<section class="filters" aria-label="Filter lifecycle cases"><label>Search cases<input id="search" type="search" placeholder="Case, data or expected outcome"></label>
<label>Process family<select id="family"><option value="">All process families</option>{family_options}</select></label>
<label>Evidence status<select id="status"><option value="">All statuses</option>{status_options}</select></label></section>
<p id="count" role="status">Showing {len(rows)} cases</p><div class="table-scroll"><table><caption>Baseline lifecycle case matrix</caption>
<thead><tr><th scope="col">Case</th><th scope="col">Process</th><th scope="col">Input / prerequisites</th><th scope="col">Expected business outcome</th><th scope="col">Evidence / status</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table></div>
<p class="muted">Generated {esc(payload['generated_at'])}. Every omitted live scenario remains not run. Original manuals and official instructions remain separate authority sources.</p></main>
<script>
const search=document.getElementById('search'),family=document.getElementById('family'),status=document.getElementById('status');
function filter(){{let visible=0;for(const row of document.querySelectorAll('tbody tr')){{row.hidden=!(row.textContent.toLowerCase().includes(search.value.toLowerCase())&&(!family.value||row.dataset.family===family.value)&&(!status.value||row.dataset.status===status.value));if(!row.hidden)visible++;}}document.getElementById('count').textContent='Showing '+visible+' cases';}}
for(const control of [search,family,status])control.addEventListener('input',filter);
</script></body></html>'''
    (folder / "index.html").write_text(content, encoding="utf-8")
    return folder / "index.html"
