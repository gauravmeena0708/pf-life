"""Every event written to the outbox is checked against its contract (contracts/events/<EventType>.schema.json) wherever the
contracts can be found — a checkout: the unit tests of every service, locally and in CI — so a payload that drifts from
its contract fails the producer's own tests instead of a consumer at run time. A deployed service carries no contracts
and skips the check (EPFO_EVENT_CONTRACTS=off turns it off anywhere; a path points it at another folder)."""
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


class ContractViolation(ValueError):
    pass


@lru_cache(maxsize=1)
def _folder() -> Path | None:
    configured = os.getenv("EPFO_EVENT_CONTRACTS", "")
    if configured.lower() == "off":
        return None
    if configured:
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts" / "events"
        if candidate.is_dir():
            return candidate
    return None


@lru_cache(maxsize=None)
def _validator(event_type: str):
    try:
        from jsonschema import Draft202012Validator
    except ImportError:                                   # a runtime image without jsonschema: nothing to check against
        return None
    folder = _folder()
    if folder is None:
        return None
    path = folder / f"{event_type}.schema.json"
    if not path.exists():
        raise ContractViolation(f"{event_type} has no contract ({path.name}); add it to docs/tools/build_gate0.py and regenerate")
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def check(envelope: dict[str, Any]) -> None:
    """Raise ContractViolation, naming every difference, if the envelope does not match its event's contract."""
    validator = _validator(envelope["event_type"])
    if validator is None:
        return
    errors = sorted(validator.iter_errors(envelope), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{'/'.join(str(p) for p in e.path) or '(envelope)'}: {e.message}" for e in errors[:8])
        message = f"{envelope['event_type']} from {envelope['producer']} breaks its contract — {detail}"
        print(f"CONTRACT VIOLATION: {message}", file=sys.stderr)       # an API turns it into a 500; this says why
        raise ContractViolation(message)
