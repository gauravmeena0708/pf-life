"""Cross-service consistency check (P2.27): the facts several services keep copies of must agree on a running stack.

Each service owns its data and learns other services' facts from events into its own tables (no cross-service reads). A
missed or wrongly applied event leaves a copy behind — the P2.14 status column too short for UNEXEMPTED_COMPLIANCE was
found that way, at run time. This script compares the copies, read-only, and lists every difference:

  exemption   — an exempted establishment's status and end date: employer (owner) vs contribution, claim, pension
  exits       — a member ID's date of exit: member (owner) vs contribution, claim, pension
  balances    — a member ID's PF balance: the contribution ledger (owner) vs claim's projection
  demands     — a 14B / 7Q / 7A demand's state and amount: contribution (owner) vs compliance
  policy      — the published rule-set versions: platform (owner) vs every service that applies them
  eps         — member IDs found not eligible for EPS (P2.19c): contribution (owner) vs pension's service record

The copies are kept by events, so they agree eventually, not at every instant: a difference is checked again (up to
RETRIES times, WAIT seconds apart) and only one that persists is reported — run straight after a test suite, the last
test's events may still be in flight.

Usage: python3 scripts/consistency_check.py [--only exits,balances] — exit status 1 when anything differs. It reads the
databases through `docker compose exec postgres psql` (PSQL overrides the command)."""
import argparse
import os
import shlex
import subprocess
import sys
import time
from collections import defaultdict

RETRIES, WAIT = int(os.getenv("CONSISTENCY_RETRIES", "3")), float(os.getenv("CONSISTENCY_WAIT", "5"))
PSQL = os.getenv("PSQL", "docker compose exec -T postgres psql -U postgres")


def rows(db: str, sql: str) -> list[list[str]]:
    out = subprocess.run([*shlex.split(PSQL), "-d", db, "-tA", "-F", "\t", "-c", sql], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"{db}: {out.stderr.strip()}")
    return [line.split("\t") for line in out.stdout.splitlines() if line.strip()]


def compare(name: str, owner: tuple[str, dict], copies: list[tuple[str, dict]], missing_ok: bool = True) -> list[str]:
    """owner and copies: (service, {key: value}). A copy that differs is a finding; a key the copy lacks is one too unless
    the copy only holds some of the keys (missing_ok)."""
    found = []
    o_name, o = owner
    for c_name, c in copies:
        for key, value in sorted(o.items()):
            if key not in c:
                if not missing_ok:
                    found.append(f"{name}: {key} — {o_name} has {value!r}, {c_name} has no copy")
            elif c[key] != value:
                found.append(f"{name}: {key} — {o_name} {value!r}, {c_name} {c[key]!r}")
        for key in sorted(set(c) - set(o)):
            found.append(f"{name}: {key} — {c_name} has {c[key]!r}, {o_name} (the owner) has no such record")
    return found


def exemption() -> list[str]:
    q = "SELECT establishment_id, status, COALESCE(ended_on::text, '') FROM {} "
    owner = {r[0]: (r[1], r[2]) for r in rows("employer_db", q.format("establishment_exemptions"))}
    copies = [(s, {r[0]: (r[1], r[2]) for r in rows(db, q.format("exempted_establishments"))})
              for s, db in (("contribution", "contribution_db"), ("claim", "claim_db"), ("pension", "pension_db"))]
    return compare("exemption", ("employer", owner), copies)


def exits() -> list[str]:
    owner = {r[0]: r[1] for r in rows("member_db", "SELECT account_link_id, COALESCE(date_of_exit::text, '') FROM employments")}
    copies = [("contribution", {r[0]: r[1] for r in rows("contribution_db", "SELECT account_link_id, COALESCE(date_of_exit::text, '') FROM establishment_members")}),
              ("claim", {r[0]: r[1] for r in rows("claim_db", "SELECT account_link_id, COALESCE(date_of_exit::text, '') FROM accounts")}),
              ("pension", {r[0]: r[1] for r in rows("pension_db", "SELECT account_link_id, COALESCE(date_of_exit::text, '') FROM eps_accounts")})]
    return compare("exit", ("member", owner), copies)          # a copy may hold only the member IDs it serves


def balances() -> list[str]:
    ledger = {r[0]: int(r[1]) for r in rows("contribution_db", """
        SELECT account_link_id, SUM(CASE WHEN side='credit' THEN amount_paise ELSE -amount_paise END)
        FROM journal_lines WHERE account_code='AC01_EPF' AND account_link_id IS NOT NULL GROUP BY account_link_id""")}
    claim = {r[0]: int(r[1]) for r in rows("claim_db", "SELECT account_link_id, employee_paise + employer_paise FROM accounts")}
    found = []                                              # opening balances are journals too (OPENING_BALANCE_BF)
    for link in sorted(set(ledger) | set(claim)):
        posted, held = ledger.get(link, 0), claim.get(link)
        if held is None:
            found.append(f"balance: {link} — the ledger holds ₹{posted / 100:,.2f}, claim has no account")
        elif held != posted:
            found.append(f"balance: {link} — ledger ₹{posted / 100:,.2f}, claim ₹{held / 100:,.2f} (difference ₹{(held - posted) / 100:,.2f})")
    return found


def demands() -> list[str]:
    q = "SELECT demand_id, state, amount_paise FROM demands"
    owner = {r[0]: (r[1], int(r[2])) for r in rows("contribution_db", q)}
    copy = {r[0]: (r[1], int(r[2])) for r in rows("compliance_db", q)}
    return compare("demand", ("contribution", owner), [("compliance", copy)], missing_ok=False)


def policy() -> list[str]:
    owner = {r[0]: r[1] for r in rows("platform_db", "SELECT rule_version, effective_from::text FROM policy_rules")}
    found = []
    for db in ("contribution_db", "claim_db", "pension_db", "compliance_db", "member_db", "employer_db", "reporting_db", "intelligence_db"):
        has = rows(db, "SELECT 1 FROM information_schema.tables WHERE table_name='policy_rules'")
        if has:
            found += compare("policy", ("platform", owner), [(db.removesuffix("_db"), {r[0]: r[1] for r in rows(db, "SELECT rule_version, effective_from::text FROM policy_rules")})],
                             missing_ok=False)
    return found


def eps() -> list[str]:
    owner = {r[0]: "NOT_ELIGIBLE" for r in rows("contribution_db", "SELECT account_link_id FROM eps_ineligible_members")}
    copy = {r[0]: "NOT_ELIGIBLE" for r in rows("pension_db", "SELECT account_link_id FROM eps_accounts WHERE NOT eps_member")}
    return compare("eps", ("contribution", owner), [("pension", copy)], missing_ok=False)


CHECKS = {"exemption": exemption, "exits": exits, "balances": balances, "demands": demands, "policy": policy, "eps": eps}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", default=",".join(CHECKS))
    args = parser.parse_args()
    total, by_check = 0, defaultdict(list)
    for name in args.only.split(","):
        by_check[name] = CHECKS[name]()
        for _ in range(RETRIES):                         # events still in flight settle within seconds
            if not by_check[name]:
                break
            time.sleep(WAIT)
            by_check[name] = CHECKS[name]()
        total += len(by_check[name])
        print(f"{name}: {'consistent' if not by_check[name] else f'{len(by_check[name])} difference(s)'}")
        for line in by_check[name][:25]:
            print(f"  - {line}")
        if len(by_check[name]) > 25:
            print(f"  … and {len(by_check[name]) - 25} more")
    print("consistent" if not total else f"{total} difference(s) across services")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
