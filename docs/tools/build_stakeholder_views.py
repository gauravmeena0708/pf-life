#!/usr/bin/env python3
"""Validate docs/stakeholder-activities.yaml and generate docs/stakeholder-api-sets.md.

Checks that every actor exists in docs/stakeholders.md, every `next` points to a real
activity, and every non-NEW endpoint exists in docs/endpoint-catalogue.md (or init.md §3.1).
Then writes, per stakeholder, the activities it performs and the API set it needs, plus the
gap lists and one Mermaid diagram per flow.

Usage: python3 docs/tools/build_stakeholder_views.py [--check]
  --check  validate only; exit 1 on errors, write nothing
"""
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

# Platform endpoints defined in init.md §3.1 but not tabled in the catalogue (all Working).
PLATFORM = [
    "GET /monitoring/claims", "GET /monitoring/contributions", "GET /monitoring/grievances",
    "GET /monitoring/data-freshness", "POST /ai/knowledge/search", "POST /ai/claims/analyse",
    "POST /ai/grievances/classify", "GET /ai/models", "POST /ai/feedback", "GET /audit/events",
    "GET /audit/correlations/{correlationId}", "GET /ndc/health",
]
STATUS_ORDER = {"W": 0, "M": 1, "P": 2, "?": 3, "NEW": 4}


def norm(endpoint):
    method, _, path = endpoint.strip().partition(" ")
    return f"{method} {path.split('?')[0].strip()}"


def load_stakeholders():
    groups, names = OrderedDict(), {}
    group = None
    for line in (DOCS / "stakeholders.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"## ([A-J])\. (.+)", line)
        if m:
            group = f"{m.group(1)}. {m.group(2)}"
            groups[group] = []
            continue
        m = re.match(r"\| `([a-z_.0-9]+)` \| ([^|]+)\|", line)
        if m and group:
            groups[group].append(m.group(1))
            names[m.group(1)] = m.group(2).strip()
    return groups, names


def load_catalogue():
    text = (DOCS / "endpoint-catalogue.md").read_text(encoding="utf-8").split("## 14.")[0]
    catalogue = {}
    for m in re.finditer(r"^\| `([A-Z]+ [^`]+)`[^|]*\|[^|]*\| (W|M|P|\?) \|", text, re.M):
        key = norm(m.group(1))
        # Keep the most-built status when one path appears with several variants.
        if key not in catalogue or STATUS_ORDER[m.group(2)] < STATUS_ORDER[catalogue[key]]:
            catalogue[key] = m.group(2)
    for endpoint in PLATFORM:
        catalogue.setdefault(endpoint, "W")
    return catalogue


def main():
    check_only = "--check" in sys.argv
    data = yaml.safe_load((DOCS / "stakeholder-activities.yaml").read_text(encoding="utf-8"))
    acts = data["activities"]
    flows = data["flows"]
    chains = data["approval_chains"]
    groups, names = load_stakeholders()
    catalogue = load_catalogue()

    errors = []
    ids = [a["id"] for a in acts]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate activity id {dup}")
    id_set = set(ids)

    by_actor = defaultdict(list)
    callers = defaultdict(set)
    new_eps = defaultdict(set)
    for a in acts:
        if a["actor"] not in names:
            errors.append(f"{a['id']}: unknown actor {a['actor']}")
        by_actor[a["actor"]].append(a)
        for n in a.get("next", []):
            if n not in id_set:
                errors.append(f"{a['id']}: next -> unknown activity {n}")
        if a.get("chain") and a["chain"] not in chains:
            errors.append(f"{a['id']}: unknown chain {a['chain']}")
        if a["id"].split(".")[0] not in flows:
            errors.append(f"{a['id']}: flow prefix not in flows")
        for ep in a.get("api", []):
            if ep.startswith("NEW "):
                new_eps[norm(ep[4:])].add(a["actor"])
            elif norm(ep) not in catalogue:
                errors.append(f"{a['id']}: endpoint not in catalogue: {ep}")
            else:
                callers[norm(ep)].add(a["actor"])
    for chain_id, chain in chains.items():
        members = [m for b in chain.get("bands", []) for m in b["chain"]] + chain.get("chain", [])
        for m in members:
            if m not in names and m not in ("maker", "checker"):
                errors.append(f"chain {chain_id}: unknown stakeholder {m}")

    no_activity = [s for s in names if s not in by_actor]
    uncalled = sorted(e for e in catalogue if e not in callers)

    if errors:
        print("ERRORS:\n  " + "\n  ".join(errors))
    print(f"{len(acts)} activities, {len(names)} stakeholders, {len(no_activity)} without activities, "
          f"{len(new_eps)} NEW endpoints, {len(uncalled)} catalogue endpoints with no caller")
    if check_only:
        sys.exit(1 if errors else 0)
    if errors:
        sys.exit(1)

    out = ["# Stakeholder API Sets", "",
           "> **Generated** by `docs/tools/build_stakeholder_views.py` from `docs/stakeholder-activities.yaml`, "
           "`docs/stakeholders.md` and `docs/endpoint-catalogue.md`. Do not edit by hand; edit the sources and re-run.", "",
           "Status of each endpoint: **W** working POC · **M** mock integration · **P** planned contract · "
           "**?** definition pending · **NEW** needed by an activity but missing from the catalogue.", ""]

    total_api = sum(1 for s in names if any(a.get("api") for a in by_actor.get(s, [])))
    out += ["## Summary", "",
            "| Measure | Count |", "|---|---|",
            f"| Stakeholders | {len(names)} |",
            f"| Activities | {len(acts)} |",
            f"| Stakeholders with at least one API | {total_api} |",
            f"| Stakeholders with activities but no API (external systems via adapters, or oversight bodies) | "
            f"{sum(1 for s in names if s in by_actor and not any(a.get('api') for a in by_actor[s]))} |",
            f"| Stakeholders with no activity yet | {len(no_activity)} |",
            f"| **NEW endpoints to add to the catalogue** | **{len(new_eps)}** |",
            f"| Catalogue endpoints no stakeholder calls | {len(uncalled)} |", ""]

    out += ["## API set per stakeholder", ""]
    for group, members in groups.items():
        out += [f"### {group}", ""]
        for s in members:
            items = by_actor.get(s, [])
            out.append(f"#### `{s}` — {names[s]}")
            out.append("")
            if not items:
                out += ["*No activity mapped yet.*", ""]
                continue
            out.append("Activities: " + "; ".join(f"**{a['id']}** {a['does']}" for a in items))
            out.append("")
            eps = OrderedDict()
            for a in items:
                for ep in a.get("api", []):
                    key = norm(ep[4:]) if ep.startswith("NEW ") else norm(ep)
                    eps.setdefault(key, "NEW" if ep.startswith("NEW ") else catalogue[key])
            adapters = sorted({a["adapter"] for a in items if a.get("adapter")})
            if eps:
                out += ["| Endpoint | Status |", "|---|---|"]
                for ep, st in sorted(eps.items(), key=lambda kv: (STATUS_ORDER[kv[1]], kv[0])):
                    out.append(f"| `{ep}` | {st} |")
                out.append("")
            if adapters:
                out += ["Integration adapters: " + ", ".join(f"`{x}`" for x in adapters), ""]

    out += ["## Gaps", "", "### NEW endpoints needed (not in the catalogue yet)", "",
            "| Endpoint | Needed by |", "|---|---|"]
    for ep in sorted(new_eps):
        out.append(f"| `{ep}` | {', '.join(f'`{s}`' for s in sorted(new_eps[ep]))} |")
    out += ["", "### Catalogue endpoints with no calling stakeholder", "",
            "Either an activity is missing from the map, or the endpoint is not needed.", ""]
    out += [f"- `{e}` ({catalogue[e]})" for e in uncalled] or ["- none"]
    out += ["", "### Stakeholders with no activity", ""]
    out += [f"- `{s}` — {names[s]}" for s in no_activity] or ["- none"]

    out += ["", "## Flow diagrams", "",
            "Each box is `actor: activity`; arrows are hand-offs (`next`). Dashed boxes are future roles.", ""]
    for flow_id, flow in flows.items():
        members = [a for a in acts if a["id"].startswith(flow_id + ".")]
        if not members:
            continue
        out += [f"### {flow_id} — {flow['name']}", "", "```mermaid", "flowchart LR"]
        seen = set()
        for a in members:
            nid = a["id"].replace(".", "_")
            label = f"{a['actor']}<br/>{a['does'][:60]}".replace('"', "'")
            out.append(f'  {nid}["{label}"]')
            if a.get("fut"):
                out.append(f"  style {nid} stroke-dasharray: 5 5")
            seen.add(a["id"])
        for a in members:
            for n in a.get("next", []):
                if n not in seen:
                    target = next(x for x in acts if x["id"] == n)
                    out.append(f'  {n.replace(".", "_")}["{target["actor"]}<br/>{target["does"][:60]}"]'.replace("'", "'"))
                    seen.add(n)
                out.append(f"  {a['id'].replace('.', '_')} --> {n.replace('.', '_')}")
        out += ["```", ""]

    (DOCS / "stakeholder-api-sets.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("wrote docs/stakeholder-api-sets.md")


if __name__ == "__main__":
    main()
