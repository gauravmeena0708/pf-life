# Lifecycle automation and data cases

A role manual explains one person's actions. A process manual follows the same claim across roles in
execution order and records the asserted business outcome. The lifecycle case matrix relates those
processes to stakeholder journeys and distinguishes specifications from verified observations.

The catalogue in `scripts/lifecycles/catalogue.py` is a finite baseline POC specification. It covers
claims, enrollment, contributions, mobility, pension, death/EDLI, grievances, compliance and ledger work.
Its data partitions include missing/invalid inputs, inclusive amount boundaries, service and exit-date
boundaries, active/exited employment, account ownership, multiple member IDs, KYC, office decisions,
interruptions, document types/size, tax and policy versions, bank failure and financial reconciliation.
It is not an exhaustive statement of actual EPFO rules or every future configured claim type.

## One-command lifecycle run

Install the browser/manual dependencies; the lifecycle requirements also install the existing common
packages for offline rule tests:

```sh
python3 -m pip install -r scripts/lifecycles/requirements.txt
python3 -m playwright install --with-deps chromium
python3 scripts/ui_manuals.py --suite all --isolated
```

The local demo must have been started once: isolation snapshots its running image IDs. The command creates
a separate Compose project, private volumes/network, copies seed/rules/realm configuration and serves the
fixture at `http://localhost:15173` (Keycloak 18080; gateway 18000). It migrates before starting consumers,
seeds the dedicated data, runs the UI cases, generates manuals and stops only that isolated project.
It does not reset/recreate the shared demo. Snapshots contain local configuration and remain in ignored
`artifacts/ui-manuals/`; do not publish them as manual downloads. Its database volumes are retained.

Use `--keep-stack` to inspect a fixture afterwards. Stop that specific fixture later with:

```sh
python3 scripts/lifecycles/isolated_stack.py --existing artifacts/ui-manuals/<epfo-lifecycle-project> --stop
```

`--existing` without `--stop` starts/reseeds that existing fixture idempotently; it does not restore spent
balances or once-only eligibility. Create a new fixture for a full run. Fixed alternate ports permit one
local isolated fixture at a time; GitHub matrix jobs use separate runners.

For a separately provisioned fresh stack, use `--suite all --base-url <fixture-url>` instead. `--suite claims`
selects only the new claim cases. `--suite smoke` is the default and retains the original return/withdrawal
and persona-switching journeys. Select a named executable data case with repeated `--case` options:

```sh
python3 scripts/ui_manuals.py --suite claims --isolated --case CLM-PAY-RETURN-REISSUE
```

The claim suite changes synthetic balances. Form 19 consumes member C's entire PF balance; Form 10C uses its
once-per-account EPS benefit. Run on dedicated fresh fixtures. Financial assertions deliberately fail if
another test changes the balance or policy concurrently. Tests never reset the main stack or repair
unrelated claims. Failure cleanup attempts to withdraw only an owned claim while withdrawal is available;
an approved/paid claim can remain for investigation. Do not blindly retry financial submissions.

## What is executed through the UI

The claim suite drives actual controls for amount validation (empty, zero, negative, fractional,
above maximum, exact maximum and unsafe integer), active/exited eligibility, amount routing through
AO/APFC/OIC bands, draft withdrawal, duplicate-open protection and another member's denied access.
Business branches include automatic settlement, reviewed settlement, return/re-scrutiny/approval,
two- and three-level final rejection, stop/restart/withdrawal, bank return with failed correction,
corrected bank details, APFC re-payment approval and successful reissue.

Document cases exercise PDF/JPEG/PNG, exact 1,000,000-byte size, over-size, unsupported MIME and mismatched
content signatures. Bank-switch coverage checks a second verified account before payment. Full-benefit
journeys cover Form 10C through its applicable office chain and Form 19 through the OIC chain, with
gross/tax/net reconciliation. The capture records the same claim reference throughout.

Settlement assertions include the terminal state, payment reference, member notice and displayed balance
change. EPS payment must not deduct the PF balance. PF payment must deduct the gross amount once; a
bank-return/reissue journey checks its full timeline and one net PF debit. Bank results and penny-drop,
signatures, OTPs, Table D and tax rules are explicit simulations/illustrative policy.

Cases for other lifecycle families are specified and linked to supporting code/tests. They are **not run**
in this UI suite; a source/test reference is not a passing result or proof of all inputs within that case.
Offline tests validate actual deterministic rule boundaries; they do not establish browser verification.

## Outputs and evidence gates

Every dated run contains:

- `manuals/index.html`: downloadable role and cross-role process manuals, in DOCX/HTML/PDF.
- `lifecycles/index.html`: searchable family/status/data-case report, with CSV and JSON exports.
- `evidence/<case>/manifest.json`: input data, same claim reference, observed stages, expected/asserted
  outcome, checked screenshots and financial observations.
- `results.xml`: JUnit status and explicit lifecycle-case properties.

The report marks a case `ui_passed` only when a matching JUnit test passes, its manifest completes the
expected outcome and its screenshot hashes/path constraints pass. A failed, skipped, absent or tampered
run cannot become verified by merely finding its test file. Tests whose fixtures fail also fail publication.
Negative cases can pass by verifying the required refusal; they do not represent successful settlement.

Generate an inventory without accessing the application:

```sh
python3 scripts/lifecycle_report.py
python3 scripts/lifecycle_report.py --run artifacts/ui-manuals/<existing-run>
python3 -m pytest -q -p no:cacheprovider scripts/ci/tests scripts/manuals/tests scripts/lifecycles/tests
```

Inventory-only reports mark every case `not_run`. Reports for existing runs preserve their evidence
locations. The UI runner publishes manuals only after its whole selected test suite passes. A failed run
still receives its case report and diagnostics but no success manual catalogue. Earlier runs remain
separate. All tests in the CI `ui` job use its own fresh runner/stack; GitHub execution is separate from
local validation.

## Adding lifecycle cases

Add an explicit catalogue row with data, prerequisites, expected outcome, integration status and a real
reference. Add a parametrized UI case where suitable; declare its case IDs and expected outcome through
the `recording` fixture. Capture checked steps, attach asserted business observations with `observe`,
and call `outcome` only after the final numerical/status assertions. The renderer automatically produces
chronological cross-role manuals alongside the role manuals. Keep distinct data cases separate instead
of treating a single success as coverage for every input or exceptional branch.

For the actual EPFO UAT project, source-manual expectations and observed portal behavior must be separate.
Only approved UAT records/actions can be used. Unavailable payment/downstream access remains a coverage
gap; a prototype payment simulation must never be counted as an actual UAT bank/payment verification.
