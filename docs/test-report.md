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

## Known limits

- Journey B spends ₹6,00,000 of member A's synthetic balance per run; after about six runs `make reset` restores it.
- Re-issue after a bank return skips the phase-2 bank-detail correction and APFC re-disbursement approval.
- De-freezing restores claims and payments; the higher post-de-freeze approval chain is phase 2.
- The AI runs with the model off in these tests; with `AI_PROVIDER=ollama` the same guards apply (unit-tested
  with a model that obeys injected instructions).
