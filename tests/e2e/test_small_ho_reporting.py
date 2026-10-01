"""Phase 2, slice 12e on the running stack: the statutory auditor reads a balanced balance sheet of the funds from the
ledger; the investment cell sees the seeded fund-manager positions against the pattern of investment; CBT, EC and FIAC
members read board packs that carry aggregates only. Read-only, so repeatable."""
import re

from tests.e2e.test_journey_a_ecr import call
from tests.e2e.test_policy_admin import browser, persona  # noqa: F401  (fixtures)


def test_balance_sheet_investments_and_board_packs(persona):
    auditor = persona("statutory-auditor", "/ho/finance/balance-sheet")
    status, r = call(auditor, "GET", "/api/v1/ho/finance/balance-sheet")
    assert status == 200 and r["data"]["balanced"] is True, r
    members = next(x for x in r["data"]["liabilities"] if x["code"] == "AC01_EPF")
    assert members["amount_paise"] > 0
    assert call(auditor, "GET", "/api/v1/ho/finance/balance-sheet?as_of=2026-13-01")[0] in (400, 422)

    cell = persona("ho-investment", "/ho/finance/investments")
    status, r = call(cell, "GET", "/api/v1/ho/finance/investments")
    assert status == 200, r
    text = str(r["data"])
    assert "GOVT_SECURITIES" in text and ("WITHIN" in text or "BELOW" in text or "ABOVE" in text), r

    for name, meeting in (("cbt-member", "CBT"), ("fiac-member", "FIAC")):
        member = persona(name, "/governance/board-packs")
        status, pack = call(member, "GET", f"/api/v1/governance/board-packs?meeting={meeting}")
        assert status == 200 and pack["data"]["meeting"] == meeting, pack
        body = str(pack["data"])                                  # synthetic UANs start 10000000; 12-digit paise amounts are fine
        assert not re.search(r"\b10000000\d{4}\b", body) and "EST-DEMO" not in body, "identifiers in a board pack"
    for name, path in (("member-a", "/api/v1/ho/finance/balance-sheet"), ("ro-oic", "/api/v1/ho/finance/investments"),
                       ("emp-owner", "/api/v1/governance/board-packs")):
        assert call(persona(name, "/"), "GET", path)[0] == 403, name
