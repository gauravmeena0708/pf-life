"""Build a standalone HTML handbook from curated notes and validated UI evidence."""
import base64
import hashlib
import html
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.handbook.content import GLOSSARY, PROCESSES, REPLAYS, SOURCES
from scripts.lifecycles.catalogue import validate_catalogue
from scripts.lifecycles.report import evidence_status
from scripts.manuals.recording import DISCLAIMER

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).parent
DEFAULT_RUN = ROOT / "artifacts/ui-manuals/20260930T091329986617Z"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def esc(value):
    return html.escape(str(value), quote=True)


def json_script(value):
    # A source string must not be able to close the script element.
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def load_replays(run, definitions=REPLAYS):
    """Fail closed: JUnit, complete manifests and all original screenshot hashes."""
    run = Path(run).resolve()
    statuses = evidence_status(run)
    loaded = []
    for definition in definitions:
        path = run / "evidence" / definition["scenario"] / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        lifecycle = manifest["lifecycle"]
        ids = lifecycle["case_ids"]
        if not ids or any(statuses.get(key, {}).get("status") != "ui_passed" for key in ids):
            raise ValueError(f"Unverified replay: {definition['scenario']}")
        if manifest["scenario"] != definition["scenario"]:
            raise ValueError("Scenario identity mismatch")
        for field, expected in definition.get("expected_fields", {}).items():
            if lifecycle.get(field) != expected:
                raise ValueError(f"Editorial example needs review: {definition['scenario']} / {field}")
        observations = lifecycle["observations"]
        # Business captures: preserve original step numbers and chronological order.
        # Repetitive persona/login/intent screens remain in the original evidence.
        skipped = {"Choose your demo persona", "Authenticate through Keycloak", "Confirm the transaction intent"}
        steps = []
        seen = set()
        for step in manifest["steps"]:
            number = step["number"]
            if not isinstance(number, int) or number in seen or (seen and number <= max(seen)):
                raise ValueError("Non-chronological or duplicate evidence step")
            seen.add(number)
            if step["title"] in skipped:
                continue
            image = path.parent / step["screenshot"]
            raw = image.read_bytes()
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Evidence is not PNG")
            steps.append({**{key: step[key] for key in ["number", "role", "title", "instruction", "expected", "captured_at", "sha256"]},
                          "image": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
                          "observations": [o for o in observations if o["step"] == number]})
        if any(o["step"] not in seen for o in observations):
            raise ValueError("Observation points to an absent evidence step")
        if not set(definition["anchors"]).issubset({step["number"] for step in steps}):
            raise ValueError("Missing PDF anchor evidence")
        loaded.append({**definition, "steps": steps, "lifecycle": lifecycle,
                       "finished_at": manifest["finished_at"], "checkout": manifest.get("checkout", {}),
                       "manifest": str(path.relative_to(run)), "manifest_sha256": digest(path),
                       "original_step_count": len(manifest["steps"]),
                       "limitations": manifest.get("limitations", [])})
    if not loaded:
        raise ValueError("No verified replays selected")
    return loaded, statuses


def source_links(keys):
    return " · ".join(f'<a href="#source-{esc(key)}">{esc(key)}</a>' for key in keys)


def recorded_cases(run, statuses):
    """Keep the reported denominator tied to the completed recording snapshot."""
    coverage = json.loads((Path(run) / "lifecycles/coverage.json").read_text(encoding="utf-8"))
    cases = coverage["cases"]
    if coverage.get("schema_version") != 1 or coverage.get("disclaimer") != DISCLAIMER:
        raise ValueError("Invalid recorded coverage catalogue")
    if len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate recorded coverage cases")
    for case in cases:
        if case["status"] != statuses.get(case["case_id"], {}).get("status", "not_run"):
            raise ValueError("Recorded coverage disagrees with validated evidence")
    return cases


def process_cards(flows):
    cards = []
    for key, item in PROCESSES.items():
        labels = [("Trigger", item["trigger"]), ("Typical handoffs", item["path"]), ("Business record", item["record"]),
                  ("Control to understand", item["control"]), ("Exceptions to ask about", item["exceptions"]), ("CTO question", item["question"])]
        rows = "".join(f'<dt>{esc(label)}</dt><dd>{esc(value)}</dd>' for label, value in labels)
        cards.append(f'<article class="process-card" id="process-{key}"><p class="eyebrow">{key} · Repository synthesis</p>'
                     f'<h3>{esc(flows[key]["name"])}</h3><dl>{rows}</dl>'
                     f'<p class="source-note">Reference keys: {source_links(item["sources"])}. Ownership in the POC: {esc(", ".join(item["services"]))}.</p>'
                     '<a class="map-link screen-only" href="#ecosystem" data-flow="'+key+'">Explore these handoffs →</a></article>')
    return "".join(cards)


def replay_print(replays):
    chapters = []
    for r in replays:
        lc = r["lifecycle"]
        timeline = "".join(f'<tr><td>{s["number"]}</td><td>{esc(s["role"])}</td><td>{esc(s["title"])}<br>'
                           f'<small>{esc("; ".join(o["stage"]+": "+o["value"] for o in s["observations"]) or s["expected"])}</small></td></tr>' for s in r["steps"])
        frames = []
        for number in r["anchors"]:
            s = next(s for s in r["steps"] if s["number"] == number)
            frames.append(f'<figure class="print-frame"><h4>Original step {number} · {esc(s["role"])}</h4>'
                          f'<img data-replay="{r["scenario"]}" data-step="{number}" alt="{esc(s["title"])}">'
                          f'<figcaption>{esc(s["title"])}. {esc(s["expected"])}<br><small>PNG SHA-256: {s["sha256"]}</small></figcaption></figure>')
        chapters.append(f'<article class="print-replay"><h3>{esc(r["title"])}</h3><p>{esc(r["lesson"])}</p>'
                        f'<p><strong>{esc(lc["claim_id"])} · {esc(lc["outcome"])}</strong><br>Cases: {esc(", ".join(lc["case_ids"]))}. '
                        f'{len(r["steps"])} selected business captures from {r["original_step_count"]} recorded steps.</p>'
                        '<p>The timeline retains every selected business capture. Four screenshot anchors follow; the portable HTML contains the full selected replay.</p>'
                        '<table><thead><tr><th>Original step</th><th>Role</th><th>Action / asserted observation</th></tr></thead><tbody>'+timeline+'</tbody></table>'
                        + "".join(frames) + '</article>')
    return "".join(chapters)


def build_html(run=DEFAULT_RUN, output=None):
    run = Path(run).resolve()
    replays, statuses = load_replays(run)
    activities_path = ROOT / "docs/stakeholder-activities.yaml"
    inventory_path = ROOT / "apps/web/src/data/system-map.generated.json"
    activity_doc = yaml.safe_load(activities_path.read_text(encoding="utf-8"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    flows = activity_doc["flows"]
    if set(PROCESSES) != set(flows):
        raise ValueError("Editorial process list is out of date")
    actors = inventory["stakeholders"]
    for activity in activity_doc["activities"]:
        if activity["actor"] not in actors:
            raise ValueError(f"Unknown stakeholder: {activity['actor']}")
    runtime = json.loads((run / "runtime.json").read_text(encoding="utf-8"))
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    # Freeze the denominator to this recording run, not the evolving checkout.
    # A newer catalogue can add cases while another agent is working in parallel.
    cases = recorded_cases(run, statuses)
    verified = sum(c["status"] == "ui_passed" for c in cases)
    not_run = sum(c["status"] == "not_run" for c in cases)
    files = [activities_path, inventory_path, ROOT / "docs/stakeholders.md", ROOT / "docs/endpoint-catalogue.md",
             ROOT / "init.md", run / "results.xml", run / "runtime.json", run / "lifecycles/coverage.json", ASSETS / "content.py", ASSETS / "build.py",
             ASSETS / "template.html", ASSETS / "handbook.css", ASSETS / "handbook.js",
             ROOT / "docs/adr/0001-gateway-bff.md", ROOT / "docs/adr/0003-ledger.md", ROOT / "docs/adr/0006-contract-generation.md",
             ROOT / "apps/gateway/app/pipeline.py", ROOT / "services/workflow-service/app/api/hr_routes.py",
             ROOT / "services/platform-service/app/api/routes.py", ROOT / "services/compliance-service/app/api/routes.py",
             ROOT / "services/contribution-service/app/infra/demands.py"]
    provenance = {"generated_at": timestamp, "checkout": {"commit": commit, "dirty": dirty}, "evidence_run": run.name,
                  "runtime": {"project": runtime["project"], "purpose": runtime["purpose"], "images": runtime["images"]},
                  "inputs": {str(p.relative_to(ROOT)): digest(p) for p in files},
                  "coverage": {"specified": len(cases), "ui_passed": verified, "not_run": not_run,
                               "scope": "Frozen case catalogue from the recorded run; excludes later additions to the working checkout",
                               "current_checkout_case_count": len(validate_catalogue())},
                  "inventory": inventory["totals"], "activity_count": len(activity_doc["activities"]),
                  "inventory_note": "Generated inventory snapshot; endpoint status is not UI-test coverage. Activity YAML is imported separately and can be newer.",
                  "sources_note": "Repository references and limited official search-index context. Direct official retrieval was unsuccessful on 30 September 2026; currency and legal applicability require source-owner review.",
                  "replays": [{k: v for k, v in r.items() if k in {"scenario", "manifest", "manifest_sha256", "finished_at", "checkout", "original_step_count"}} for r in replays]}
    data = {"processes": PROCESSES, "flows": flows, "activities": activity_doc["activities"], "inventory": inventory,
            "replays": replays, "glossary": GLOSSARY, "provenance": provenance}
    source_rows = "".join(f'<tr id="source-{esc(k)}"><th scope="row">{esc(k)}</th><td>'
                          + (f'<a href="{esc(url)}">{esc(title)}</a>' if url else esc(title)+" — see the repository source register / activity definitions for context")
                          + '</td><td>Repository reference; current content / applicability not independently verified.</td></tr>' for k, (title, url) in SOURCES.items())
    glossary_rows = "".join(f'<tr><th scope="row">{esc(term)}</th><td>{esc(full)}</td><td>{esc(meaning)}</td></tr>' for term, full, meaning in GLOSSARY)
    overview = "".join(f'<li><strong>{key} · {esc(item["short"])}</strong><span>{esc(item["path"])}</span></li>' for key, item in PROCESSES.items())
    replacements = {"CSS": (ASSETS / "handbook.css").read_text(), "JS": (ASSETS / "handbook.js").read_text(), "DATA": json_script(data),
                    "PROCESSES": process_cards(flows), "PRINT_REPLAYS": replay_print(replays), "GLOSSARY": glossary_rows,
                    "SOURCES": source_rows, "MAP_ALTERNATIVE": overview, "DATE": timestamp[:10], "RUN": esc(run.name),
                    "VERIFIED": str(verified), "SPECIFIED": str(len(cases)), "NOT_RUN": str(not_run),
                    "ROLES": str(len(actors)), "INTERFACES": str(len(inventory["interfaces"])),
                    "ACTIVITIES": str(len(activity_doc["activities"])), "PROVENANCE": esc(json.dumps(provenance, indent=2, ensure_ascii=False)),
                    "DISCLAIMER": DISCLAIMER}
    document = (ASSETS / "template.html").read_text(encoding="utf-8")
    for key, value in replacements.items():
        document = document.replace("@@"+key+"@@", value)
    if "@@" in document:
        raise ValueError("Unresolved template marker")
    if output is None:
        output = ROOT / "artifacts/cto-handbook" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    target = output / "epfo-cto-handbook.html"
    target.write_text(document, encoding="utf-8")
    (output / "build.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return target


def export_pdf(target):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route("http://**/*", lambda route: route.abort())
        page.route("https://**/*", lambda route: route.abort())
        page.goto(target.as_uri(), wait_until="load")
        page.evaluate("window.preparePrint()")
        page.wait_for_function("Array.from(document.querySelectorAll('.print-frame img')).every(i=>i.complete && i.naturalWidth>0)")
        page.pdf(path=str(target.with_suffix(".pdf")), format="A4", print_background=True, prefer_css_page_size=True,
                 tagged=True, outline=True,
                 display_header_footer=True, header_template='<div></div>',
                 footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#334155">PF Life · Synthetic CTO orientation · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        browser.close()
    return target.with_suffix(".pdf")
