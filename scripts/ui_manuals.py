#!/usr/bin/env python3
"""Run UI tests and generate role-specific POC manuals from their verified screenshots."""
import argparse
import os
import subprocess
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ci.stack_checks import check_results
from scripts.manuals.render import build_manuals
from scripts.lifecycles.report import write_report


def capture_and_render(args, output):
    if not args.render_only:
        output.mkdir(parents=True, exist_ok=False)
        env = dict(os.environ, UI_BASE_URL=args.base_url.rstrip("/"), UI_MANUAL_OUTPUT=str(output),
                   UI_HEADED="1" if args.headed else "0", UI_CASE_IDS=",".join(args.case))
        if getattr(args, "fixture", None):
            shutil.copyfile(args.fixture / "provenance.json", output / "runtime.json")
            env["UI_RUNTIME_PROVENANCE"] = str(output / "runtime.json")
        else:
            from scripts.lifecycles.readiness import wait_for_sign_in
            wait_for_sign_in(args.base_url)
        print(f"UI evidence and manuals: {output}", flush=True)
        targets = {"smoke": ["tests/ui/test_claim_review.py", "tests/ui/test_persona_switching.py"],
                   "claims": ["tests/ui/test_claim_lifecycle.py"], "all": ["tests/ui"]}[args.suite]
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets,
                                 f"--junitxml={output / 'results.xml'}"], cwd=ROOT, env=env)
        if result.returncode:
            print(f"Lifecycle case report: {write_report(output, output)}", flush=True)
            print("UI verification failed. Evidence retained; verified manuals were not generated.", file=sys.stderr)
            return result.returncode
    check_results(output / "results.xml")
    index = build_manuals(output, pdf=not args.no_pdf)
    if not (output / "lifecycles").exists():
        print(f"Lifecycle case report: {write_report(output, output)}", flush=True)
    print(f"Verified manuals: {index}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:5173", help="URL of the already running synthetic UI")
    parser.add_argument("--output", type=Path, help="New output directory (default: artifacts/ui-manuals/<UTC timestamp>)")
    parser.add_argument("--headed", action="store_true", help="Show the browser during the test")
    parser.add_argument("--no-pdf", action="store_true", help="Generate DOCX and HTML only")
    parser.add_argument("--render-only", type=Path, help="Render a previously verified evidence directory without rerunning tests")
    parser.add_argument("--suite", choices=["smoke", "claims", "all"], default="smoke",
                        help="smoke preserves the original non-payment journeys; claims exercises settlement and changes synthetic balances")
    parser.add_argument("--case", action="append", default=[], help="Select lifecycle case ID; repeat for several cases (claims/all suite)")
    parser.add_argument("--isolated", action="store_true", help="Snapshot running local demo images into a fresh private fixture on port 15173")
    parser.add_argument("--keep-stack", action="store_true", help="Keep the isolated fixture running after verification")
    args = parser.parse_args()
    if args.case and args.suite == "smoke":
        parser.error("--case requires --suite claims or --suite all")
    if args.render_only and args.isolated or args.keep_stack and not args.isolated:
        parser.error("--isolated requires a live run; --keep-stack requires --isolated")
    output = args.render_only.resolve() if args.render_only else (args.output or ROOT / "artifacts/ui-manuals" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    fixture = None
    try:
        if args.isolated:
            from scripts.lifecycles.isolated_stack import prepare, start
            fixture = prepare()
            start(fixture)
            args.base_url = "http://localhost:15173"
            args.fixture = fixture
        return capture_and_render(args, output)
    finally:
        if fixture and not args.keep_stack:
            from scripts.lifecycles.isolated_stack import run
            print(f"Stopping only isolated fixture {fixture.name}; its volumes and snapshots remain.", flush=True)
            run(fixture, "down")


if __name__ == "__main__":
    raise SystemExit(main())
