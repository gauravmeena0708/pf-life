# pf-life — an EPFO platform, imagined and vibe-coded

> **This is a vibe-coded app.** Almost every line here was written by AI coding agents (Claude Code, OpenAI Codex
> and agy) working from prompts, with a person choosing what to build, reading the sources
> and approving each change. It has not been written or reviewed line by line the way production code is. Read it as a
> working sketch of what a modern provident-fund platform could look like, not as code to deploy.
>
> In hindsight the repository should have been called **pf-vibe**.

> **Synthetic demonstration — not an official EPFO system.** No real member, employer or government data; no connection
> to EPFO, Aadhaar, banks, DigiLocker or any other real service (every outside system is a labelled mock). Rates,
> ceilings and limits live in an illustrative, versioned rule set (`config/demo-rules.yaml`), not in the code, and are
> not statements of current law.

## What it is

A proof of concept of the Employees' Provident Fund Organisation's work as one platform: members, employers, field and
zonal offices, Head Office, pensioners, nominees and outside bodies, each with their own login and screens, served by
API-first microservices.

- **15 services** (FastAPI, async SQLAlchemy, PostgreSQL per service) talking through events (outbox / inbox over
  RabbitMQ), behind a gateway that checks every call against a permission map; a React + TypeScript web app.
- **115 stakeholders, 82 demo logins, ~490 catalogued endpoints and 109 event contracts**, all generated from a few
  source files (`docs/endpoint-catalogue.md`, `docs/stakeholder-activities.yaml`) so the docs, the gateway routes and the
  contracts cannot drift apart.
- **Grounded in EPFO's own documents**: the manuals (accounting, audit, compliance, recovery, exemption, pension, EDLI),
  Head Office circulars and SOPs, PIB releases and the Code on Social Security — each feature cites what it follows
  (`docs/phase-2-plan.md`, `docs/stakeholders.md` → Sources).

Covered, among much else: ECR filing and payment, the ledger and interest, claims through the officer chain with
step-up confirmation, transfers (including the automatic one), death and EDLI claims, pensions from Form 10D to the PPO
and monthly payment, higher pension, exempted trusts, compliance and recovery (7A, 14B, 7Q, 8B–8G), PMVBRY, the ₹25,000
ceiling of 2026, grievances, vigilance and audit, a retirement forecast, and an advisory AI that never takes decisions.

## Run it

Needs Docker (with Compose) and Python 3 (for the seed and test scripts); Node only to work on the web app outside Docker.

```bash
make up        # build and start everything (creates .env from .env.example with development values)
make migrate   # create every service's tables
make seed      # load the synthetic members, employers, offices and logins
make demo      # print the URLs
```

Open <http://localhost:5173> and pick a persona (member, employer, dealing assistant, APFC, pensioner, nominee …);
every demo password is `Demo@2026!`. `docs/demo-script.md` walks through the journeys screen by screen. `make reset`
wipes the data and starts again.

## How it is tested

| Suite | Command |
|---|---|
| Unit tests of every service and shared package (SQLite; every event checked against its contract) | `make test` |
| Web app: types, lint, component tests | `cd apps/web && npx tsc --noEmit -p . && npx eslint src && npx vitest run` |
| End to end on the running stack (Playwright) | `make e2e` |
| Must-deny security tests | `make security` |
| Cross-service consistency of copied facts | `make consistency` |
| UI lifecycle suites that also generate the role manuals | `python3 scripts/ui_manuals.py --suite smoke` |
| Docs and contracts in sync with their sources | `make check-docs` |

CI runs the unit suites on every push and a fresh-stack verification (migrations from empty, e2e, UI) after it.
Results and what each slice proved are in `docs/test-report.md`.

## Where things are

| Path | What |
|---|---|
| `init.md` | The original build brief given to the agents |
| `docs/phase-2-plan.md` | The plan, slice by slice: what was built, from which source, and what is still pending |
| `docs/architecture.md`, `docs/adr/` | Architecture and its decisions |
| `docs/endpoint-catalogue.md` | Every EPFO function the platform covers, with its status (working, mock, planned) |
| `docs/stakeholders.md`, `docs/stakeholder-activities.yaml` | Who does what, through which API — the source of permissions and routes |
| `docs/stakeholder-atlas.html` | The same as an interactive map |
| `docs/event-catalogue.md`, `contracts/` | Events, their JSON Schemas and the OpenAPI contracts |
| `docs/demo-script.md`, `docs/test-report.md` | How to demonstrate it; how it was tested |
| `config/demo-rules.yaml` | The illustrative, versioned rules (rates, ceilings, limits, approval chains) |
| `services/`, `apps/`, `packages/` | The services, the gateway and web app, the shared libraries |
| `scripts/` | Seeding, consistency check, UI manuals, mock feeds |

## Use

For learning and discussion. Nothing here is endorsed by EPFO or the Government of India, and nothing in it is advice.
