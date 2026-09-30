"""The test's assertions and screenshots are the evidence for each manual instruction."""
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

DISCLAIMER = "SYNTHETIC DEMONSTRATION — NOT AN OFFICIAL EPFO SYSTEM"
ROOT = Path(__file__).resolve().parents[2]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def checkout() -> dict:
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


class Recording:
    def __init__(self, output: Path, scenario: str, title: str, purpose: str, scope: str,
                 prerequisites: list[str], limitations: list[str], lifecycle: dict | None = None):
        self.folder = output / "evidence" / scenario
        self.folder.mkdir(parents=True, exist_ok=False)
        self.manifest = {
            "schema_version": 1, "scenario": scenario, "title": title, "purpose": purpose,
            "scope": scope, "prerequisites": prerequisites, "limitations": limitations,
            "disclaimer": DISCLAIMER, "started_at": now(), "status": "running",
            "checkout": checkout(), "steps": [],
        }
        if lifecycle is not None:
            self.manifest["lifecycle"] = {**lifecycle, "observations": []}
        if os.getenv("UI_RUNTIME_PROVENANCE"):
            self.manifest["runtime"] = json.loads(Path(os.environ["UI_RUNTIME_PROVENANCE"]).read_text(encoding="utf-8"))
        self.save()

    def save(self) -> None:
        target = self.folder / "manifest.json"
        temporary = self.folder / "manifest.tmp"
        temporary.write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(target)

    def step(self, page, role: str, title: str, instruction: str, expected: str, check, focus=None) -> None:
        check()  # If the observable result fails, this instruction is never recorded as verified.
        if focus is not None:
            focus.scroll_into_view_if_needed()
        number = len(self.manifest["steps"]) + 1
        filename = f"{number:02d}.png"
        page.screenshot(path=str(self.folder / filename), animations="disabled", full_page=False, mask_color="#003366",
                        mask=[page.locator(selector) for selector in
                              ("#password", ".persona code", ".demo-otp code", "#stepup-otp", "input[name=account_number]")])
        url = urlsplit(page.url)
        self.manifest["steps"].append({
            "number": number, "role": role, "title": title, "instruction": instruction,
            "expected": expected, "url": f"{url.scheme}://{url.netloc}{url.path}",
            "captured_at": now(), "screenshot": filename,
            "sha256": hashlib.sha256((self.folder / filename).read_bytes()).hexdigest(),
        })
        self.save()

    def observe(self, stage: str, value: str, check) -> None:
        """Attach an asserted business observation to the most recent captured screen."""
        check()
        if not self.manifest.get("lifecycle") or not self.manifest["steps"]:
            raise ValueError("Lifecycle observations need a lifecycle and a captured screen")
        self.manifest["lifecycle"]["observations"].append({
            "stage": stage, "value": value, "step": len(self.manifest["steps"]), "at": now(),
        })
        self.save()

    def outcome(self, value: str, check) -> None:
        self.observe("Outcome", value, check)
        self.manifest["lifecycle"]["outcome"] = value
        self.save()

    def finish(self, passed: bool) -> None:
        lifecycle = self.manifest.get("lifecycle")
        if lifecycle and lifecycle.get("outcome") != lifecycle.get("expected_outcome"):
            passed = False
        self.manifest["status"] = "passed" if passed and self.manifest["steps"] else "failed"
        self.manifest["finished_at"] = now()
        self.save()

    def failure(self, page, label: str) -> None:
        """Keep the failed screen separately; it is never included as a verified manual step."""
        try:
            filename = f"failure-{label}.png"
            page.screenshot(path=str(self.folder / filename), animations="disabled", timeout=5000, mask_color="#003366",
                            mask=[page.locator(selector) for selector in
                                  ("#password", ".persona code", ".demo-otp code", "#stepup-otp", "input[name=account_number]")])
            self.manifest.setdefault("diagnostics", []).append({
                "screen": label, "screenshot": filename,
                "headings": page.get_by_role("heading").all_text_contents(),
                "alerts": page.get_by_role("alert").all_text_contents(),
            })
            self.save()
        except Exception as error:
            print(f"Could not capture the failed {label} screen: {type(error).__name__}")
