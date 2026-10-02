#!/usr/bin/env python3
"""Publish the latest verified user manuals into the web portal (apps/web/public/manuals/, not committed).

scripts/ui_manuals.py writes each run to artifacts/ui-manuals/<run>/ with manuals/ (HTML and Word, catalogue.json) and
lifecycles/ (the lifecycle case report). This copies the newest run whose catalogue is verified, so the portal's
/manuals page can list them; the web container serves public/ as it is."""
import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts" / "ui-manuals"
TARGET = ROOT / "apps" / "web" / "public" / "manuals"


def latest_verified(runs: Path) -> Path | None:
    for run in sorted((p for p in runs.glob("*") if p.is_dir()), reverse=True):
        catalogue = run / "manuals" / "catalogue.json"
        if catalogue.is_file() and json.loads(catalogue.read_text(encoding="utf-8")).get("status") == "verified":
            return run
    return None


def publish(run: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for part in ("manuals", "lifecycles"):
        if (run / part).is_dir():
            shutil.copytree(run / part, target / part)
    (target / "published.json").write_text(json.dumps({"run": run.name, "published_at": datetime.now(UTC).isoformat()}) + "\n",
                                           encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="a run folder under artifacts/ui-manuals (default: the newest verified one)")
    args = parser.parse_args()
    run = args.run or latest_verified(RUNS)
    if not run:
        print("No verified manuals under artifacts/ui-manuals; run scripts/ui_manuals.py first.", file=sys.stderr)
        return 1
    publish(run, TARGET)
    print(f"Published {run.name} to {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
