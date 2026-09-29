# Test report

**Run:** 27 September 2026, on a clean stack (`make reset && make up && make migrate && make seed`), commit on
branch `slice5/claude`. Everything is synthetic; the model was off (`AI_PROVIDER=disabled`).

| Suite | Command | Result |
|---|---|---|
| Unit — shared packages | `make test` | 25 passed |
| Unit — gateway | `make test` | 23 passed |
| Unit — services (13) | `make test` | 157 passed: employer 12, member 12, contribution 22, claim 19, payment-simulator 12, workflow 18, grievance 10, audit 8, reporting 15, intelligence 20, pension 3, platform 3, mock-integrations 3 |
| End to end (Gate 1, Journeys A–E, dashboards) | `make e2e` | 18 passed¹ |
| Must-deny security | `make security` | 18 passed, covering all 25 rows of `docs/permissions.md` (21 on the running stack, 4 by the named unit tests) |
| Failure and restart | `make resilience` | 3 passed: broker down, consumer down, gateway restart |
| Fresh-database migrations | throwaway Postgres, `alembic upgrade head` per service | all 10 database-backed services migrate from empty |
| Docs and contracts in sync | `make check-docs` | clean |

¹ The dashboards test failed on the first clean run and passed after two fixes: it had assumed events already
existed (it sorts first), and the zone dashboard computed a repository-only fallback path inside the container
(HTTP 500). Both are fixed in the same commit as this report.

## What the end-to-end tests prove

| Journey | Test | Highlights |
|---|---|---|
| Gate 1 | `test_gate1_walking_skeleton.py` (9) | No token reaches the browser; CSRF; planned endpoints answer 501; internal JWT verified by services |
| A — ECR | `test_journey_a_ecr.py` (3) | Verify, grant, upload, validate, approve, submit (idempotent), pay via mock bank, passbook; revoked operator refused within 5 s |
| B — claim | `test_journey_b_claim.py` (2) | ₹6,00,000 claim through DA → SS → APFC; bank return and re-issue; timeline, notices, passbook withdrawal; member B denied |
| C — grievance | `test_journey_c_grievance.py` (1) | Document, office confidentiality, reply with evidence, escalation to zone, resolution with step-up, metrics, hash-chained audit trail |
| D — suspicious activity | `test_journey_d_security.py` (1) | Advisory signal on new device → contact change → claim; shared kiosk is context only; CAIU review with no automatic action; reviewed recovery; session and signatory revocation |
| E — assistant | `test_journey_e_assistant.py` (1) | Sourced answers from verified documents; refusal about other members; planted injection ignored; structured officer analysis requiring review; model off |
| Read models | `test_dashboards.py` (1) | Claims, contributions, freshness, public statistics with suppression, zone dashboard; role checks |

## Coverage of the catalogue

370 operations in `docs/endpoint-catalogue.md`:

| Status | Phase 1 | Later phases |
|---|---|---|
| W — working | 88 | — |
| M — mock adapter | 9 | 18 |
| P — planned (answers 501 `/problems/planned`) | — | 249 |
| ? — definition pending | — | 6 |

Phase 1 is complete: every phase-1 operation is either built or behind a labelled mock. Three phase-2 freeze
operations moved to W as the first tier-2 process (`config/processes/member-freeze.yaml`).

## Update — policy administration (27 September 2026)

After adding policy administration (`/ho/config/rule-sets`) the suites were run again on the same stack:
every unit test passes (platform-service 9 new, shared policy module 15 new, plus policy tests in claim,
contribution, workflow and intelligence services), and 38 end-to-end and security tests pass, including
`tests/e2e/test_policy_admin.py` (a new claim type with its own approval chain, in force today; the wage ceiling
raised to ₹25,000 from next month).

## Update — money under policy, Joint Declaration, closed shortcuts (28 September 2026)

After Joint Declaration (the second tier-2 process), re-disbursement after a bank return, the post-de-freeze
approval chain, and policy-driven interest, TDS and pensions, the suites were run again on the same stack:

| Suite | Result |
|---|---|
| Unit — shared packages | 40 passed |
| Unit — gateway | 23 passed |
| Unit — services (13) | 188 passed: employer 12, member 15, contribution 28, claim 24, payment-simulator 12, workflow 24, grievance 10, audit 8, reporting 15, intelligence 21, pension 6, platform 10, mock-integrations 3 |
| End to end | 24 passed, including `test_policy_money.py` (a revised interest rate credits only the difference; a changed TDS rate applies to the next payment; a higher minimum pension revises a pension in payment with arrears) and `test_joint_declaration.py` |
| Must-deny security | 18 passed (DENY-15/22 now re-approve the claim through the stricter after-de-freeze chain) |

Found and fixed on the way: a second pension revision from the same date paid arrears already paid by the first
(arrears now count what each month has received); the same pension change carried into a scheduled version and
into today's version proposed two revisions (now one); the publication guard refused any earlier change under a
scheduled version even when that version already carried it, and refused a same-day correction.

## Update — Phase 2, slice 1: exits and transfers (28 September 2026)

Unit tests 259 passed (services 196, 8 of them new: member 4, workflow 2, contribution 1, claim 1; packages 40; gateway 23); end to end 26 passed
(including `test_exit_transfer.py`); must-deny 18 passed. Found on the way: the catalogue did not mark the member's
transfer request as needing step-up while the process asked for one (the gateway would never pass the
confirmation), and employer exit marking was marked the other way round; both now agree.

## Update — Phase 2, slice 2: registration and KYC (28 September 2026)

Unit tests 268 passed (services 205, including member 24, contribution 31, claim 26, workflow 27; packages 40; gateway 23);
must-deny 18 passed; end to end 27 passed on a freshly reset stack (`make reset`). The reset cleared two
data leftovers of the long-running stack (member A's used-up synthetic balance; an interest credit posted to a
transferred member ID before that defect was fixed) and showed that the exit, transfer and registration tests
assumed the employer grants Journey A creates; they now set them up themselves.

## Update — Phase 2, slice 3: pension office and pensioner services (29 September 2026)

Unit tests 271 passed (pension-service 9); end to end 30 passed (including `test_pension_services.py`);
must-deny 18 passed. Found on the way: the pensioner could not make a declaration (the endpoint was granted only to
family pensioners) and the DA (Pension) could not see overdue certificates; both grants were added.

## Update — Phase 2, slice 4: pension settlement (29 September 2026)

Unit tests 274 passed (pension-service 12); end to end 32 passed (including `test_pension_settlement.py`);
must-deny 18 passed. Found on the way: a one-officer-per-claim rule would have stopped the APFC (Pension) from
e-signing a PPO whose worksheet they approved, which the Pension Manual expects; the rule is now maker ≠ checker
for each step. The DA (Pension) was not allowed by the gateway to propose the initial arrear; granted.

## Update — Phase 2, slice 6a: the establishment record, changes and OLRE (30 September 2026)

Unit tests 298 passed; end to end 42 passed (including `test_establishment.py`); must-deny 18 passed.

## Update — Phase 2, slice 5d: claim scrutiny as in the CITES manuals (30 September 2026)

Unit tests 294 passed; end to end 40 passed (including `test_cites_claim_rules.py`; the whole suite was run twice
on the same stack to check it can be re-run); must-deny 18 passed.

## Update — Phase 2, slice 5c: ledger locks, signed Form 13, establishment freeze, Annexure K (29 September 2026)

Unit tests 293 passed; end to end 39 passed (including `test_ledger_and_establishment.py`, run on a stack freshly
reset with `make reset`); must-deny 18 passed.

## Update — Phase 2, slice 5b: death and EDLI claims, the PRO counter (29 September 2026)

Unit tests 286 passed; end to end 36 passed (including `test_death_claims.py`); must-deny 18 passed.

- The deceased member is seeded at UAN 100000000901 / AL-0901. UANs from …900 and member IDs from AL-0900 are
  reserved for such cases and skipped by the registration allocator: seed data that sat inside the allocator's
  range was written over a joinee registered by an earlier e2e run on a long-lived stack.

## Update — Phase 2, slice 5a: claim lifecycle and office tools (29 September 2026)

Unit tests 279 passed; end to end 34 passed (including `test_claim_lifecycle.py`); must-deny 18 passed.

## Known limits

- Journey B spends ₹6,00,000 of member A's synthetic balance per run; after about six runs `make reset` restores it.
- Journey B, the TDS test and the must-deny tests spend synthetic balances; `make reset` restores them.
- Interest is credited on month-end balances of the seeded ledger only; interest up to the date of a settlement
  (for a claim paid mid-year) is not computed. TDS is a flat illustrative rate, not the Income-tax Act; Form 15H's
  age condition is not checked. Pensions are recomputed from stored salary and service (no service aggregation);
  a revision is approved by one APFC (Pension) instead of DA → SS → APFC.
- The AI runs with the model off in these tests; with `AI_PROVIDER=ollama` the same guards apply (unit-tested
  with a model that obeys injected instructions).
