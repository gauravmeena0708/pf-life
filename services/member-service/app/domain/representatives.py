"""P2.24: Authorised representatives domain rules, scopes, and subject resolution."""
import json
import os
from pathlib import Path

SCOPES = [
    "VIEW_PROFILE",
    "VIEW_PASSBOOK",
    "VIEW_CLAIMS",
    "VIEW_SERVICE_HISTORY",
    "TRACK_GRIEVANCES",
    "RAISE_GRIEVANCE",
]

RELATIONS = ["GUARDIAN", "AGENT"]

SEED_FILE = os.environ.get("SEED_FILE", "/srv/seed/synthetic.json")


def load_keycloak_subjects() -> dict[str, str]:
    for candidate in [
        Path(SEED_FILE),
        Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json",
    ]:
        if candidate.exists():
            try:
                with open(candidate, encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("keycloak_subjects", {})
            except Exception:
                pass
    return {"rep-demo": "00000000-0000-4000-8000-000000000083"}


def resolve_representative_subject(
    representative_subject: str | None,
    representative_username: str | None,
) -> str | None:
    # The synthetic service has no Keycloak admin API. Only the seeded representative
    # login can be appointed; an arbitrary UUID must never become an authority grant.
    allowed = {load_keycloak_subjects().get("rep-demo")}
    if representative_subject and representative_subject.strip():
        subject = representative_subject.strip()
        return subject if subject in allowed else None
    if representative_username and representative_username.strip():
        subjects = load_keycloak_subjects()
        subject = subjects.get(representative_username.strip())
        return subject if subject in allowed else None
    return None
