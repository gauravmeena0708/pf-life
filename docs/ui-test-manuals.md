# UI tests and generated user manuals

For comprehensive case specifications, cross-role process manuals and dedicated settlement fixtures,
see [Lifecycle automation](lifecycle-automation.md). The original smoke command below remains available.

Run one command against an already running, seeded synthetic stack:

```sh
python3 scripts/ui_manuals.py
```

The runner uses Chromium to click the actual account menus, navigation menus, claim forms, officer queues,
docket controls and confirmation dialogs. The tests submit business commands through the visible UI;
they do not bypass the forms with direct API calls or substitute mock browser responses.

It produces a dated directory under `artifacts/ui-manuals/` containing the JUnit test result, screenshot
evidence and an `index.html` linking the role manuals in **DOCX, HTML and PDF**. The HTML files contain their
own screenshots and can be opened offline. Screenshots are SHA-256 checked before rendering.

The DOCX structure follows the reference manuals in `../manuals`: title and role, version control chart,
contents, purpose, scope, prerequisites, numbered instructions, screenshot figures and disclaimer.
The reference manuals are read for structure; their text and images are not copied into these POC manuals.
Every generated manual identifies the synthetic POC and its actual observed coverage.

## Smoke suite coverage (the default `--suite smoke`)

This table covers only the default smoke run. `--suite claims` adds the claim lifecycle cases, and the full case
matrix (135 cases across claims, enrollment, contributions, mobility, pension, death/EDLI, grievances, compliance,
ledger controls and oversight) is in [Lifecycle automation](lifecycle-automation.md), where each case names the
test that exercises it.

| Workflow | Actual UI checks | Generated role manuals |
|---|---|---|
| Form 31 medical advance | Choose an eligible claim, enter amount, review the officer chain, confirm and track submission | Member |
| Claim scrutiny | Open the assigned queue case, generate CAD before acting, complete scrutiny checks and forward the recommendation | Initiator — DA Accounts |
| Return for correction | Generate a fresh CAD, enter a return reason, confirm the decision, inspect action history | Reviewing officer |
| Withdrawal | Track the claim and withdraw it before final approval | Included in Member |
| Persona switching | Member → security analyst → employer through real Keycloak logout/login; check landing pages and visible role gates | Portal user |

The default claim is ₹1,00,001, above the baseline automatic threshold and within the DA → AO approval band.
The reviewer returns it to the initiator, then the member withdraws it. This exercises an officer decision
without paying or depleting the synthetic balance. It does not demonstrate final approval or disbursement.
Member A needs sufficient eligible employee balance and no existing open medical advance. The tests never
reset the demo, alter existing claims, or recreate grants. On failure, they attempt to withdraw only the claim
they created; the failed evidence remains available for diagnosis.

## Installation and options

```sh
python3 -m pip install -r scripts/manuals/requirements.txt
python3 -m playwright install --with-deps chromium
python3 scripts/ui_manuals.py --base-url http://localhost:5173 --headed
```

Use `--no-pdf` for DOCX and HTML only. Use `--output <new-directory>` to choose an output folder. Each run
uses a new directory, so a failed run cannot leave a previous manual looking newly verified.
The Python runner supports Python 3.12 or newer. The Docker stack remains on its repository-defined version.

`UI_DEMO_PASSWORD` can override the synthetic password without placing it in the command line. The claim
amount and reviewer can be overridden together with `UI_CLAIM_AMOUNT` and `UI_REVIEWER` when running a
different illustrative policy (for example, `600000` and `ro-ss` for the baseline three-step chain).
The test asserts that the claim is routed to officers; an unexpected automatic approval fails the run.

Previously verified captures can be rendered later, provided their JUnit report passes and no `manuals/`
directory has already been published:

```sh
python3 scripts/ui_manuals.py --render-only <captured-run-directory>
```

The runner fails if a test fails, is skipped, or runs no tests. Rendering also refuses failed or incomplete
scenario manifests and missing or changed screenshots. Passwords and one-time codes are masked in the
screenshots; captions contain the observed page path without authentication query parameters.

## Continuous verification

The `ui` matrix job in `.github/workflows/stack.yml` provisions its own fresh stack and runs the same command.
Its `stack-ui-*` artifact includes the manuals, evidence, test results and stack diagnostics. Other suites
have their own runners, so their grants, policy changes and payments do not interfere with manual capture.
Artifacts are retained for seven days. A generated manual proves the steps captured in that run; it does not
prove full interface coverage, official statutory correctness, or production readiness.

## Extending coverage

Add a UI test under `tests/ui/`. Use the `recording` fixture to declare purpose, scope, prerequisites and
limitations. After each meaningful action, call `record.step(...)` with the role, instruction, expected
result and an assertion callback. The assertion runs before the screenshot. Tests are marked passed only
after fixture cleanup also succeeds; the renderer groups the verified steps into separate role manuals.
Keep dependent steps in one test, with separate authenticated browser contexts for each officer.

Recorder and renderer checks run without the application:

```sh
python3 -m pytest -q -p no:cacheprovider scripts/ci/tests scripts/manuals/tests
```

The automation uses [Playwright assertions](https://playwright.dev/python/docs/test-assertions) to wait for
observable UI results and [python-docx](https://python-docx.readthedocs.io/en/latest/user/quickstart.html)
to build the editable Word manuals. PDF output is printed from the same HTML using Chromium.
