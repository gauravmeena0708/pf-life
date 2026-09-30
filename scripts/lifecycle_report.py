#!/usr/bin/env python3
"""Generate a case inventory, or assess an existing UI run without rerunning it."""
import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.lifecycles.report import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="Existing UI evidence run; omitted means all cases not run")
    parser.add_argument("--output", type=Path, help="New report directory")
    args = parser.parse_args()
    output = (args.output or ROOT / "artifacts/ui-manuals" / ("inventory-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))).resolve()
    output.mkdir(parents=True, exist_ok=False)
    print(write_report(output, args.run.resolve() if args.run else None))


if __name__ == "__main__":
    main()
