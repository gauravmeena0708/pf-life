# Fresh-stack verification

`.github/workflows/stack.yml` runs on pushes, pull requests and manual dispatch. It complements the existing
unit, frontend and contract checks in `ci.yml`.

Each suite (`tests/e2e`, `tests/security`, `tests/resilience`, `tests/ui`) runs on a separate GitHub-hosted Ubuntu runner,
with its own Compose project and initially empty volumes. Suites run serially within their runner because they
change shared seeded balances, policies and grants; they do not share data with the other runners.

The workflow builds the application, starts PostgreSQL, Redis and RabbitMQ, and runs `alembic upgrade head`
in a one-off container for each configured service with `DATABASE_URL`. Application services and event
consumers start only after every migration succeeds. This catches migrations that work on an existing demo
database but fail on an empty one. Services are discovered from Compose, including newly added services;
a database service without an Alembic configuration fails the check.

Compose waits for service health checks. An additional bounded check waits for the imported Keycloak realm,
gateway readiness and Vite before seeding. AI remains disabled and all integrations use the synthetic mocks.
Playwright Chromium and its system dependencies are installed explicitly. A successful suite must also have
a nonempty JUnit report with no skipped tests, so a missing dependency cannot silently bypass verification.

The run uploads the JUnit report, existing journey screenshots, container status and the last 200 log lines
per container, retained for seven days. Cleanup removes only that runner's Compose project and volumes.

The helper tests can be run locally without Docker or the demo stack:

```sh
python3 -m pytest -q -p no:cacheprovider scripts/ci/tests
```

The stack workflow uses the existing tests' fixed localhost ports and the private subnets in `compose.yaml`.
Run it on a disposable runner; a second Compose project on the demo host would still collide on ports and
subnets. It does not invoke `make reset` against the shared development stack.

The UI job also generates role-specific Word, HTML and PDF manuals from the successful browser tests; see
[UI tests and manuals](ui-test-manuals.md). Its evidence and manuals are included in the job artifact.

The workflow is added as a check; making its four jobs required for merges is a separate repository setting.
It exercises the existing journey tests, which include authenticated API calls from the browser and selected
UI interactions. It does not establish complete UI coverage or production readiness.
