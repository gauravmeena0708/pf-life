"""Employer-side rules: which grants a role may hold, and the mock registry check. No framework imports."""
import re

GRANTS_BY_KIND = {
    # operator = employer sub-user who prepares returns; never approves or submits (init.md §5 Journey A2)
    "OPERATOR": {"ecr.prepare", "members.manage"},
    # signatory = approves, submits and pays (Journey A5)
    "SIGNATORY": {"ecr.approve", "ecr.submit", "payment.initiate"},
    "OWNER": {"establishment.manage", "operators.manage", "signatories.manage"},
}
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


class RuleError(ValueError):
    def __init__(self, code: str, message: str, fix: str) -> None:
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix


def check_grants(kind: str, grants: list[str]) -> list[str]:
    allowed = GRANTS_BY_KIND[kind]
    unknown = sorted(set(grants) - allowed)
    if not grants:
        raise RuleError("no-grants", "Choose at least one permission.", f"Allowed for {kind.lower()}: {', '.join(sorted(allowed))}.")
    if unknown:
        raise RuleError("grant-not-allowed", f"{', '.join(unknown)} cannot be given to a {kind.lower()}.",
                        f"Allowed for {kind.lower()}: {', '.join(sorted(allowed))}.")
    return sorted(set(grants))


def mock_registry_check(establishment: dict, evidence: dict) -> tuple[bool, str]:
    """Deterministic MOCK of PAN / GSTIN registries. Never calls a real registry."""
    pan, gstin = (evidence.get("pan") or "").upper(), (evidence.get("gstin") or "").upper()
    if not PAN_RE.match(pan):
        return False, "PAN format is not valid (expected 5 letters, 4 digits, 1 letter)."
    if pan != establishment["pan"]:
        return False, "PAN does not match the establishment record (mock registry)."
    if gstin and (not GSTIN_RE.match(gstin) or gstin[2:12] != pan):
        return False, "GSTIN is not valid or does not contain the establishment PAN (mock registry)."
    return True, "PAN verified against the mock registry" + (" and GSTIN matches" if gstin else "")
