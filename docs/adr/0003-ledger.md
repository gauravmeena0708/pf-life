# ADR-0003: Double-entry, immutable, integer-paise ledger

- **Status:** Accepted (Gate 0, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** Money must never be lost, duplicated or silently edited; production shows legacy migration gaps and duplicate postings.

**Decision.** `contribution-service` owns a double-entry journal with the chart of accounts in `init.md` §4.1. Amounts are integers in paise. Journals are append-only; corrections are reversing journals. A deferred database trigger rejects unbalanced journals. Each journal has a unique business key (payment ID, claim ID) so a duplicate event cannot post twice.

**Alternatives.** Balance columns updated in place (no audit trail); decimals (acceptable, but integers remove rounding questions).

**Consequences.** Passbook and balances are projections; every posting is traceable to its cause; other services never write money.
