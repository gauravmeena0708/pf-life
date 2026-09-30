#!/usr/bin/env python3
"""Fresh-stack CI checks. Docker operations inherit the workflow's Compose project and files."""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINTS = (
    "http://localhost:8080/realms/epfo-demo/.well-known/openid-configuration",
    "http://localhost:8000/health/ready",
    "http://localhost:5173/",
)


def migration_services(config: dict, root: Path = ROOT) -> list[str]:
    """Use the configured services, so a newly added database service is included automatically."""
    services = []
    for name, service in config["services"].items():
        if "DATABASE_URL" not in (service.get("environment") or {}):
            continue
        if not (root / "services" / name / "alembic.ini").is_file():
            raise ValueError(f"{name} has DATABASE_URL but no services/{name}/alembic.ini")
        services.append(name)
    if not services:
        raise ValueError("No database services found in the Compose configuration")
    return sorted(services)


def migrate() -> None:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True,
    )
    for service in migration_services(json.loads(result.stdout)):
        print(f"Migrating fresh database: {service}", flush=True)
        # One-off containers run Alembic only: no API server or messaging consumers yet.
        subprocess.run(
            ["docker", "compose", "run", "--rm", "--no-deps", service, "alembic", "upgrade", "head"],
            cwd=ROOT, check=True,
        )


def wait_for_entry_points(timeout: float = 180) -> None:
    """Compose health checks do not cover Keycloak realm import, the gateway, or Vite."""
    deadline = time.monotonic() + timeout
    pending = set(ENTRY_POINTS)
    while pending and time.monotonic() < deadline:
        for url in sorted(pending):
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    if response.status == 200:
                        pending.remove(url)
                        print(f"Ready: {url}", flush=True)
            except (urllib.error.URLError, TimeoutError):
                pass
        if pending:
            time.sleep(2)
    if pending:
        raise RuntimeError("Browser entry points did not become ready: " + ", ".join(sorted(pending)))


def check_results(path: Path) -> None:
    """Missing dependencies can skip Playwright modules; that must never pass the stack gate."""
    report = ET.parse(path).getroot()
    cases = list(report.iter("testcase"))
    if not cases:
        raise ValueError("The stack suite ran no tests")
    bad = [case for case in cases if any(case.find(tag) is not None for tag in ("skipped", "failure", "error"))]
    if bad or any(int(suite.get(field, "0")) for suite in report.iter("testsuite")
                  for field in ("skipped", "failures", "errors")):
        raise ValueError("The stack suite has skipped or unsuccessful tests")
    print(f"Verified {len(cases)} successful stack tests with no skips", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Migrate configured service databases before starting the application")
    commands.add_parser("wait", help="Wait for the imported Keycloak realm, gateway and web app")
    results = commands.add_parser("results", help="Reject an empty, skipped or unsuccessful JUnit report")
    results.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "wait":
        wait_for_entry_points()
    else:
        check_results(args.path)


if __name__ == "__main__":
    main()
