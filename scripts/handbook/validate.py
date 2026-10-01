#!/usr/bin/env python3
"""Check the portable handbook with HTTP(S) blocked and export its PDF."""
import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.handbook.build import export_pdf


def validate(target, pdf=True):
    from playwright.sync_api import sync_playwright
    raw = target.read_text(encoding="utf-8")
    payload = re.search(r'<script id="handbook-data" type="application/json">(.*?)</script>', raw, re.S)
    assert payload, "Missing embedded data"
    data = json.loads(payload.group(1))
    captures = 0
    for journey in data["replays"]:
        for step in journey["steps"]:
            assert hashlib.sha256(base64.b64decode(step["image"].split(",", 1)[1])).hexdigest() == step["sha256"], "Embedded PNG changed"
            captures += 1
    errors, requests = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        def block(route):
            requests.append(route.request.url)
            route.abort()
        context.route("http://**/*", block)
        context.route("https://**/*", block)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(target.as_uri(), wait_until="load")
        assert page.locator('#map .map-node').count() == 14
        assert page.locator('#role-rows tr').count() == len(data["inventory"]["stakeholders"])
        page.screenshot(path=str(target.parent / "review-desktop.png"))
        page.locator('#map [data-node="F03"]').focus()
        page.locator('#map [data-node="F03"]').press('Enter')
        assert page.locator('#map-flow').input_value() == 'F03'
        assert 'Contributions' in page.locator('#node-detail').inner_text() or 'ECR' in page.locator('#node-detail').inner_text()
        page.locator('#map-flow').select_option('F04')
        page.locator('#map-view').select_option('roles')
        assert page.locator('#map .map-node').count() > 3
        page.locator('#map-search').fill('__no_matching_role__')
        assert page.locator('#map-status').inner_text().startswith('0 /')
        page.locator('#map-clear').click()
        page.locator('#map [data-node="member"]').click()
        assert 'F04 activities' in page.locator('#node-detail').inner_text()
        page.screenshot(path=str(target.parent / "review-graph.png"))
        page.locator('#map-flow').select_option('F03')
        page.locator('#map-view').select_option('services')
        page.locator('#map [data-node="contribution-service"]').click()
        assert 'poc service ownership synthesis' in page.locator('#node-detail').inner_text().lower()
        page.locator('.role-directory summary').click()
        page.locator('#role-search').fill('fo.ao')
        assert page.locator('#role-rows tr').count() > 0
        assert page.locator('#role-rows tr').count() < len(data["inventory"]["stakeholders"])
        for index, journey in enumerate(data["replays"]):
            page.locator('#replay-select').select_option(str(index))
            assert page.locator('#replay-prev').is_disabled()
            for i, step in enumerate(journey["steps"]):
                page.locator('#replay-timeline button').nth(i).click()
                page.wait_for_function("document.getElementById('replay-image').complete && document.getElementById('replay-image').naturalWidth > 0")
                assert f'Original step {step["number"]}' in page.locator('#replay-position').inner_text()
                assert step["sha256"] in page.locator('#replay-evidence').text_content()
                assert page.locator('#replay-image').get_attribute('src') == step["image"]
            assert page.locator('#replay-next').is_disabled()
            page.locator('#replay-prev').click()
            assert not page.locator('#replay-next').is_disabled()
            page.locator('#replay-next').click()
        page.locator('#replay-select').select_option('1')
        page.locator('#replay-timeline button').filter(has_text=re.compile(r'^24$')).click()
        page.locator('#replay-image').scroll_into_view_if_needed()
        page.screenshot(path=str(target.parent / "review-replay.png"))
        page.locator('#replay-open').click()
        assert page.locator('#screenshot-dialog').is_visible()
        page.locator('#screenshot-close').click()
        page.locator('#glossary-search').fill('universal')
        assert page.locator('#glossary-table tbody tr:visible').count() == 1
        # Print must retain the entire glossary even after an interactive filter.
        page.evaluate('window.preparePrint()')
        assert page.locator('#glossary-table tbody tr:visible').count() == len(data["glossary"])
        page.wait_for_function("Array.from(document.querySelectorAll('.print-frame img')).every(i=>i.complete && i.naturalWidth>0)")
        assert page.locator('.print-frame img').count() == 24
        assert page.locator('#print-map .map-node').count() == 14
        assert page.locator('body').evaluate('(b)=>b.scrollWidth<=window.innerWidth'), 'Desktop overflow'
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator('#overview').scroll_into_view_if_needed()
        page.screenshot(path=str(target.parent / "review-mobile.png"))
        assert page.locator('body').evaluate('(b)=>b.scrollWidth<=window.innerWidth'), 'Mobile overflow: '+str(page.evaluate('({width:innerWidth,body:document.body.scrollWidth})'))
        assert not errors, errors
        assert not requests, requests
        browser.close()
    result = {"status": "passed", "standalone_http_requests": requests, "browser_errors": errors,
              "replays_checked": len(data["replays"]), "embedded_pngs_checked": captures,
              "print_anchors": 24, "viewports": ["1440x1000", "390x844"],
              "checks": ["keyboard graph selection", "role handoffs", "graph search", "service ownership", "role directory search",
                         "every replay step / embedded PNG hash", "previous / next controls", "full-size screenshot dialog",
                         "glossary search / print reset", "offline assets", "desktop / mobile overflow"]}
    if pdf:
        export_pdf(target)
        result["pdf"] = target.with_suffix('.pdf').name
    (target.parent / 'validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    parser.add_argument('--no-pdf', action='store_true')
    args = parser.parse_args()
    validate(args.html.resolve(), not args.no_pdf)
