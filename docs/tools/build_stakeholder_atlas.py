#!/usr/bin/env python3
"""Build docs/stakeholder-atlas.html, the interactive stakeholder and lifecycle explorer.

Reads docs/stakeholder-activities.yaml, docs/stakeholders.md and docs/endpoint-catalogue.md,
embeds them as JSON into docs/tools/explorer_template.html and writes the page.

Usage: python3 docs/tools/build_stakeholder_atlas.py
"""
import json
import re
from pathlib import Path

import yaml

from build_stakeholder_views import DOCS, PLATFORM, STATUS_ORDER, norm

TEMPLATE = Path(__file__).with_name("explorer_template.html")
OUT = DOCS / "stakeholder-atlas.html"


def clean(text):
    return re.sub(r"\*\*|`", "", text).strip()


def persona(mark):
    """Turn the register's ✔ / ➕ marks into words for the page."""
    if not mark or mark == "—":
        return ""
    return mark.replace("✔", "seeded").replace("➕", "to add").strip()


def stakeholders():
    groups, rows = [], []
    group = None
    for line in (DOCS / "stakeholders.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"## ([A-J])\. (.+)", line)
        if m:
            group = f"{m.group(1)}. {m.group(2).strip()}"
            groups.append(group)
            continue
        m = re.match(r"\| `([a-z_.0-9]+)` \|(.+)\|\s*$", line)
        if not (m and group):
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        if group.startswith("J."):  # ID | Stakeholder | Role for EPFO | Future | Src
            name, today, future, poc = cells[0], cells[1], cells[2], ""
        else:  # ID | Stakeholder | Today | Future | POC | Src
            name, today, future, poc = cells[0], cells[1], cells[2], cells[3]
        rows.append({
            "id": m.group(1), "name": clean(name), "group": group, "today": clean(today),
            "future": clean(future), "poc": persona(clean(poc)),
            "fut": bool(re.search(r"\bNew\b", future)),
        })
    return groups, rows


def endpoints():
    text = (DOCS / "endpoint-catalogue.md").read_text(encoding="utf-8").split("## 14.")[0]
    eps = {}
    for m in re.finditer(r"^\| `([A-Z]+ [^`]+)`[^|]*\|([^|]*)\| (W|M|P|\?) \| (\d) \| ([^|]*)\|", text, re.M):
        key = norm(m.group(1))
        entry = {"status": m.group(3), "phase": m.group(4), "owner": m.group(5).strip(), "fn": clean(m.group(2))}
        if key not in eps or STATUS_ORDER[entry["status"]] < STATUS_ORDER[eps[key]["status"]]:
            eps[key] = entry
    for ep in PLATFORM:
        eps.setdefault(ep, {"status": "W", "phase": "1", "owner": "see init.md §3.1", "fn": "Platform endpoint from init.md §3.1"})
    return eps


def main():
    data = yaml.safe_load((DOCS / "stakeholder-activities.yaml").read_text(encoding="utf-8"))
    groups, people = stakeholders()
    eps = endpoints()
    acts = []
    for a in data["activities"]:
        acts.append({
            "id": a["id"], "flow": a["id"].split(".")[0], "actor": a["actor"], "does": a["does"],
            "api": [norm(e) for e in a.get("api", [])], "next": a.get("next", []), "chain": a.get("chain"),
            "adapter": a.get("adapter"), "event": a.get("event"), "src": str(a.get("src", "")),
            "ev": a.get("ev", "U"), "fut": bool(a.get("fut")),
        })
    payload = {
        "groups": groups, "stakeholders": people, "activities": acts, "flows": data["flows"],
        "chains": data["approval_chains"], "endpoints": eps,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", blob)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(DOCS.parent)} ({len(html) // 1024} KB): "
          f"{len(people)} stakeholders, {len(acts)} activities, {len(eps)} endpoints")


if __name__ == "__main__":
    main()
