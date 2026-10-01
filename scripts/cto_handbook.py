#!/usr/bin/env python3
"""Generate a portable CTO handbook; validated recorded evidence is required."""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.handbook.build import DEFAULT_RUN, ROOT, build_html, export_pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN, help="Completed UI-manual run containing JUnit and recorded evidence")
    parser.add_argument("--output", type=Path, help="New output directory (must not exist)")
    parser.add_argument("--no-pdf", action="store_true", help="Generate standalone HTML only")
    parser.add_argument("--publish-web", action="store_true", help="Also publish HTML and PDF to the Vite frontend public directory")
    args = parser.parse_args()
    if args.publish_web and args.no_pdf:
        parser.error("--publish-web requires PDF export")
    target = build_html(args.run, args.output)
    print(target)
    if not args.no_pdf:
        pdf = export_pdf(target)
        print(pdf)
        if args.publish_web:
            destination = ROOT / "apps/web/public/cto-handbook"
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, destination / pdf.name)
            shutil.copy2(target, destination / "index.html")
            print(destination / "index.html")


if __name__ == "__main__":
    main()
