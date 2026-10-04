#!/usr/bin/env python3
"""Generate gateway routes from the repository endpoint catalogue and grants."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "docs" / "tools"))
from build_gate0 import load_catalogue  # noqa: E402

OUTPUT = ROOT / "apps" / "gateway" / "app" / "routes.generated.json"
SERVICE_NAMES = {"payment-simulator": "payment-simulator"}


def route_regex(path: str) -> str:
    parts = re.split(r"(\{[^{}]+\})", path)
    result = "".join("[^/]+" if part.startswith("{") else re.escape(part) for part in parts)
    return "^" + result + "$"


def main() -> None:
    permissions = yaml.safe_load((ROOT / "docs" / "permissions.yaml").read_text(encoding="utf-8"))["stakeholders"]
    callers_by_endpoint: dict[str, list[str]] = {}
    for stakeholder, grant_rows in permissions.items():
        for grant in grant_rows or []:
            callers_by_endpoint.setdefault(grant["endpoint"], []).append(stakeholder)

    # Tier-2 processes (ADR-0005): the contract keeps its owner, but the engine in workflow-service serves it.
    engine_ops = {op["operation"] for d in (yaml.safe_load(p.read_text(encoding="utf-8"))
                                            for p in sorted((ROOT / "config" / "processes").glob("*.yaml")))
                  for op in d["operations"]}
    routes = []
    for key, op in load_catalogue().items():
        owner = op["owner"]
        if key in engine_ops:
            upstream = "http://workflow-service:8000"
        elif owner == "gateway":
            upstream = None
        elif owner == "platform":
            upstream = "http://platform-service:8000"
        else:
            service = SERVICE_NAMES.get(owner, f"{owner}-service")
            upstream = f"http://{service}:8000"
        path = op["path"]
        routes.append({
            "method": op["method"],
            "path_template": path,
            "regex": route_regex(path),
            "status": op["status"],
            "phase": op["phase"],
            "owner": owner,
            "upstream": upstream,
            "money": op["money"],
            "step_up": op["step_up"],
            # "About me" routes (/security/me/...) are open to every authenticated caller; they only ever
            # return the caller's own data. "*" = any authenticated stakeholder.
            "callers": ["*"] if op["path"].startswith(("/security/me/", "/security/step-up-challenges")) else sorted(set(callers_by_endpoint.get(key, []))),
            "summary": op["summary"],
            "revocation": path in {
                "/employers/me/operators/{operatorId}/revocations",
                "/employers/me/signatories/{signatoryId}/revocations",
                "/employers/me/payroll-providers/authorisations/{grantId}/revocations",   # P2.22: cut a provider off at once
            },
        })
    routes.sort(key=lambda r: (-len(r["path_template"].replace("{", "").replace("}", "")), r["path_template"], r["method"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(routes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(routes)} routes to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
