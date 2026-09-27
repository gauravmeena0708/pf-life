from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def load_permissions() -> dict:
    path = ROOT / "docs" / "permissions.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["stakeholders"]


def stakeholder_for_claims(claims: dict, valid_roles: set[str]) -> str | None:
    realm_roles = claims.get("realm_access", {}).get("roles", [])
    return next((role for role in realm_roles if role in valid_roles), None)
