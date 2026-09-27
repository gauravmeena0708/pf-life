# Architecture

> Gate 0 document (`init.md` §10). It states how the POC is built: backend, API layer, frontend, identity and tokens, data, messaging and runtime. Decisions with alternatives are recorded as ADRs in `docs/adr/`. Contracts are in `contracts/`; the endpoint list is `docs/endpoint-catalogue.md`.
>
> **SYNTHETIC DEMONSTRATION — NOT AN OFFICIAL EPFO SYSTEM.** No real personal data, no real integrations.

## 1. Shape of the system

```text
Browser (React SPA, persona switcher, guided tour, behind-the-scenes drawer)
   │  HttpOnly session cookie only — no tokens in the browser
   ▼
Gateway / BFF  (apps/gateway, FastAPI)            ◄── Keycloak (OIDC, identity + coarse roles)
   │  session → access token → actor context → revocation check → permission check
   │  → step-up check → internal JWT (60 s, one audience) → forward
   ▼
Business services (FastAPI, one database each)
  employer · member · contribution · claim · payment-simulator · pension (mock)
  workflow (incl. process engine) · grievance · audit · reporting · intelligence
   │                ▲
   │ outbox         │ inbox (dedupe)
   ▼                │
RabbitMQ topic exchange `epfo.events`  ──►  per-consumer queues + DLQ
   │
Mock integrations (bank, UIDAI, NPCI, Jeevan Pramaan, MCA): signed, deterministic, scenario switches
```

Clients never reach a service or a database directly. Services never read or write another service's database. Cross-service writes happen through events; the few synchronous cross-service reads go through service-to-service tokens (§5.5).

## 2. Backend

### 2.1 Service template

Every service has the same layout so that agents cannot drift:

```text
services/<name>/
  app/
    api/          routers — thin: parse, authorise, call domain, map errors
    domain/       entities, state machines, rules; no framework imports
    infra/        SQLAlchemy models + repositories, outbox relay, inbox consumer, adapters
    main.py       FastAPI app; mounts shared middleware
  migrations/     Alembic
  tests/          unit + service-level integration (testcontainers)
  pyproject.toml  pinned dependencies
  Dockerfile
```

Stack: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, aio-pika, httpx, structlog, OpenTelemetry.

Shared packages (`packages/`) contain **no business logic**: `common-auth-client` (verify internal JWT, read actor context, require scope), `common-observability` (logging, tracing, correlation ID, Problem Details, envelope, idempotency middleware), `domain-contracts` (Pydantic models generated from `contracts/events/`).

### 2.2 Standard tables in every service database

| Table | Purpose |
|---|---|
| `outbox` | Events written in the same transaction as the state change; a relay publishes them and marks them sent |
| `inbox` | `event_id` of every consumed event; a duplicate delivery is acknowledged and ignored |
| `idempotency_keys` | `(actor, operation, key)` → stored response; a retried command returns the original result |
| `audit_local` | This service's audit records, shipped to `audit-service` through the outbox |

Every aggregate has a `version` column; commands require `If-Match` and fail with `409` on mismatch.

### 2.3 Three ways an endpoint becomes real (ADR-0005)

| Tier | Mechanism | Examples |
|---|---|---|
| 1. Hand-built domain | Full domain code in the owning service | ECR and ledger, claims, payments, grievances, revocation, risk signals, AI |
| 2. Process engine | Declarative process definitions (YAML) executed by the engine in `workflow-service`: states, transitions, allowed roles, approval chain, form schema, emitted events. The owning service registers its definitions and receives a callback event when a process completes | Joint Declaration, freeze / de-freeze, 14B/7Q knock-off, TRRN adjustment, IDS → worksheet → PPO, recovery steps, audit paras, vigilance, legal cases, exemption decisions, DSC approval |
| 3. Read models | Projections in `reporting-service` built from events | District / Zonal / HO / board dashboards, e-report card, pendency |

Anything else stays a **planned** contract: the gateway answers `501 /problems/planned` from the catalogue, so services need no stubs.

When a process moves from tier "planned" to tier 2, its catalogue row changes from **P** to **W** with owner unchanged; the engine is an implementation detail behind the owning service's contract.

### 2.4 Ledger (ADR-0003)

`contribution-service` owns a double-entry journal. Amounts are integer paise. Journals are immutable: corrections are reversing journals. A database constraint (deferred trigger) rejects any journal whose debits and credits differ. The chart of accounts and posting rules are in `init.md` §4.1. Every journal carries the business key that caused it (payment ID, claim ID) with a unique index, so a duplicate event can never post twice.

### 2.5 Rules

`config/demo-rules.yaml` (labelled `ILLUSTRATIVE_ONLY`) is versioned. A decision or filing loads one frozen rule version and stores it with the input snapshot and calculation trace, so any decision can be replayed. Approval-chain bands come from the same file.

### 2.6 Locks (ADR-0004)

Member-ledger and wage-month locks are Redis leases (`SET key NX PX`) with a TTL, a heartbeat and a **fencing token**. Writes under a lock present the token; the database rejects a write with an older token. Keys, states and transitions are defined in `workflow-service.yaml` (`LockKeyPattern`, `LockLifecycle`).

### 2.7 Messaging

One topic exchange `epfo.events`; routing key = event type (`claim.ClaimSubmitted.v1`). Each consumer has its own durable queue and dead-letter queue. Retries use exponential backoff (5 attempts), then DLQ. `GET /ndc/event-failures` lists DLQ messages; `POST /ndc/event-failures/{eventId}/replays` re-publishes one. Consumers are idempotent through the inbox table and tolerate out-of-order delivery by checking aggregate versions.

### 2.8 Mock integrations

`payment-simulator` is the mock bank (it owns the catalogue's bank callback endpoints). One `mock-integrations` container implements the other adapters: UIDAI, NPCI, Jeevan Pramaan and MCA. Responses are deterministic from seeded data. Callbacks to the platform are signed (HMAC-SHA256 over body + timestamp + nonce) and a nonce store rejects replays. A scenario endpoint (`dev` profile only) forces outcomes — bank return, penny-drop failure, face-auth mismatch — for demos and tests. Every mock response carries `"mock": true`.

## 3. API layer — the gateway (ADR-0001, ADR-0002)

`apps/gateway` (FastAPI) is the only entry point. Its route table is **generated from the catalogue** (`owner` → upstream service; `status` → planned handling), so paths cannot drift from the contracts.

Per request:

1. **Session** — read the `__Host-epfo-session` cookie; load the session from Redis (encrypted); refresh the access token if it expires within 60 s.
2. **Actor context** — subject from the validated access token; grants, office posting, jurisdiction and establishment scope fetched from the owning services and cached for 30 s (`init.md` §6.1).
3. **Revocation** — check the revocation set (§5.4). Fail closed if Redis is down (public pages still served).
4. **Permission** — `docs/permissions.yaml`: is this stakeholder allowed this endpoint; which scope rule applies.
5. **Step-up** — for 🔐 operations, validate the step-up token against subject, action, resource version and amount; consume it.
6. **Planned** — if the catalogue status is P or ?, return `501 /problems/planned` with the contract summary.
7. **Forward** — mint an internal JWT and proxy to the owning service with `X-Correlation-Id`.

Conventions (all services, enforced by shared middleware): base `/api/v1`; `{data, meta}` envelope; RFC 9457 errors; cursor pagination (`?cursor=&limit=`); `ETag` / `If-Match`; `Idempotency-Key` on 💰 commands; UTC timestamps; opaque IDs.

**Contract-first.** `contracts/openapi/<service>.yaml` is the contract. Each service's generated FastAPI schema is compared with it in CI (Schemathesis + a path/operation diff); a mismatch fails the build. Hand-written schemas are added through `contracts/openapi/overlays/` and merged by `docs/tools/build_gate0.py`.

**Behind the scenes.** Every call returns `X-Correlation-Id`. The web app's drawer calls `GET /audit/correlations/{correlationId}`, which lists every API hop, state transition, event and journal line produced by one user action.

## 4. Frontend

| Concern | Choice |
|---|---|
| Build | React 18, TypeScript, Vite |
| API client | `openapi-typescript` types + `openapi-fetch`, generated from `contracts/openapi/gateway-consolidated.yaml` |
| Data | TanStack Query (cache, retries, `If-Match` from ETags) |
| Routing | React Router; one route module per interface (21) |
| Forms | react-hook-form + zod (schemas generated from OpenAPI) |
| Components | Radix primitives + own design tokens; WCAG 2.1 AA; no colour-only meaning |
| i18n | react-i18next, English and Hindi label scaffolding |
| Tests | Vitest (units), Playwright (Journeys A–E; also the demo script) |

App shell:

- **Persona switcher** — a real logout and login as the chosen persona through Keycloak (demo passwords shown only on the demo login page). No impersonation.
- **Menus from permissions** — `GET /security/me/permissions` decides what is shown; the backend still enforces everything.
- **Status badges** — every screen and action shows Working / Mock / Planned from the catalogue; planned screens render the contract (purpose, chain, phase) instead of fake data.
- **Generic process screens** — one queue / case / decision screen renders any tier-2 process from its definition (form schema, chain, allowed actions).
- **Guided tour** — JSON scripts per journey (step, persona, target element, expected state); **Reset demo** reseeds.
- **Behind-the-scenes drawer** — the correlation trace (§3).
- **Negative demos** — buttons that attempt a forbidden action and show the denial (from `docs/permissions.md` must-deny list).
- **Step-up modal** — shows exactly what is being authorised; demo OTP displayed and labelled.
- **Demo banner** — "SYNTHETIC DEMONSTRATION — NOT AN OFFICIAL EPFO SYSTEM" on every page.

## 5. Identity and tokens

### 5.1 Keycloak realm `epfo-demo`

| Client | Flow | Used by |
|---|---|---|
| `epfo-bff` (confidential) | Authorization code + PKCE | Gateway, for all browser users |
| `b2b-sandbox` | Client credentials | Payroll-provider demo |
| `mock-integrations` | Client credentials (+ signed callbacks) | Mock bank, Jeevan Pramaan, MCA |
| `svc-<name>` (one per service) | Client credentials | Rare synchronous service-to-service reads |

Users are the 24 personas of `init.md` §6.2.1, imported from `infra/keycloak/realm-epfo-demo.json`. Keycloak holds identity and coarse realm roles (the stakeholder ID). Domain grants — establishments an operator may act for, an officer's posting and amount band — live in the owning services, where they are audited and revocable.

### 5.2 Browser session

- Authorization code + PKCE between gateway and Keycloak; tokens stored server-side in Redis, encrypted with a key from the environment.
- Browser receives only `__Host-epfo-session` (HttpOnly, Secure, SameSite=Strict, Path=/). Mutating requests also carry a CSRF token header (double submit).
- Access token 5 min; refresh token rotating with reuse detection, 30 min idle, 8 h maximum. The gateway refreshes silently.
- Keycloak back-channel logout ends the gateway session.

### 5.3 Internal token (ADR-0002)

The gateway signs a JWT (Ed25519) per forwarded request: `iss=gateway`, `aud=<service>`, `exp=60 s`, `sub`, `stakeholder`, `grants`, `office_id`, `jurisdiction`, `establishment_id`, `step_up` (if consumed), `correlation_id`. Services verify it against the gateway's JWKS (`/internal/jwks`, `services` network only). Plain `X-Actor-*` headers are never trusted.

### 5.4 Revocation

Per `init.md` §6.6: the gateway writes the revocation set synchronously when a revocation route succeeds; events rebuild it after a restart; entries are grant-scoped or subject-wide; checked on every request; services re-check grants on writes and sensitive reads. Target: denial within 5 s, tested.

### 5.5 Service-to-service

Default is events. A synchronous read (e.g. member-service asking workflow-service for a member's active locks for `account-status`) uses a client-credentials token for `svc-<caller>`; the callee accepts only the callers listed for that route.

### 5.6 Step-up

`POST /security/step-up-challenges` with action, resource ID, resource version, amount and summary hash → demo OTP (displayed) or Keycloak re-authentication (`max_age=0`) → `…/verifications` → token (5 min, single use, bound to all of the above) stored in Redis and consumed by the gateway.

### 5.7 Partners and callbacks

Client-credentials tokens plus HMAC-signed bodies with timestamp and nonce; replay store in Redis (10 min window). Callback endpoints are idempotent by provider event ID.

## 6. Data

- One PostgreSQL 16 container; one database and one login role per service; `pg_hba.conf` restricts each role to its own database and its own network subnet (`init.md` §2.4).
- Object store (SeaweedFS, S3 API — ADR-0008): private buckets per service (`claim-docs`, `grievance-docs`, `ai-corpus`); presigned URLs issued only after an authorisation check; malware-scan adapter stub, fail-closed when enabled.
- Redis: sessions, revocation set, step-up tokens, lock leases, rate limits, replay nonces. Never financial truth.
- Seed data: `scripts/seed_synthetic_data.py`, deterministic (fixed seed and IDs) so the guided tour always finds the same member, filing and claim. No real PII; names and numbers are generated and marked synthetic.

## 7. Runtime

| Mode | Command | Contents | Approx. memory |
|---|---|---|---|
| Full | `make up` | Every service in its own container + Keycloak, PostgreSQL, RabbitMQ, Redis, object store, mock-integrations, gateway, web | ~3 GB |
| Lite | `make up-lite` | Same images; Python services run with one worker and low connection pools; observability and AI profiles off | ~2 GB |
| AI | `COMPOSE_PROFILES=ai` | Adds Ollama | + model size |
| Observability | `COMPOSE_PROFILES=observability` | Prometheus, Grafana, Jaeger | + ~0.7 GB |

Ports and networks: `init.md` §2.4. Health: `/health/live`, `/health/ready` on every service; `GET /ndc/health` aggregates them.

## 8. Testing

| Level | Tool | Gate |
|---|---|---|
| Unit | pytest, Vitest | every PR |
| Service integration | pytest + testcontainers (real PostgreSQL, RabbitMQ, Redis) | every PR |
| Contract | Schemathesis against each service; OpenAPI diff vs `contracts/` | every PR |
| Security negatives | pytest in `tests/security/` — the 25 must-deny tests of `docs/permissions.md` | Gate 3+ |
| Resilience | broker down, service restart between commit and publish, duplicate callbacks, DLQ replay | Gate 5 |
| End-to-end | Playwright, Journeys A–E | Gate 2+ (per journey) |

## 9. Delivery slices

| Slice | Content | Clickable result |
|---|---|---|
| 1 Walking skeleton | Compose, Keycloak + 24 personas, gateway BFF, service template ×11 with health, web shell with persona switcher and 21 interface shells, CI | Log in as anyone; browse every interface with correct status labels |
| 2 Journey A | employer, member, contribution, mock bank, ledger, revocation ≤ 5 s | Full ECR flow across four personas |
| 3 Journey B | claim, workflow approval chains, payment, return / re-disburse | Claim through DA → SS/AO → APFC/OIC to payment and back |
| 4 Journeys C + D | grievance, audit trail, risk signals, step-up, signatory revocation, recovery | Escalation; suspicious-activity handling |
| 5 Journey E + engine + dashboards | intelligence (AI optional), process engine (tier 2), read models (tier 3), hardening, demo script | Complete demo + test report |

## 10. ADR index

| ADR | Decision |
|---|---|
| [0001](adr/0001-gateway-bff.md) | Single FastAPI gateway as BFF; tokens stay server-side |
| [0002](adr/0002-internal-jwt.md) | Gateway-signed internal JWT between gateway and services |
| [0003](adr/0003-ledger.md) | Double-entry, immutable, integer-paise ledger owned by contribution-service |
| [0004](adr/0004-lock-leases.md) | Redis lock leases with TTL and fencing tokens |
| [0005](adr/0005-process-engine.md) | Declarative process engine for maker-checker office processes |
| [0006](adr/0006-contract-generation.md) | Contracts generated from the catalogue, hand detail through overlays |
| [0007](adr/0007-local-runtime.md) | Local Docker Compose runtime on one laptop; full and lite modes |
| [0008](adr/0008-object-store.md) | SeaweedFS as the S3-compatible object store (MinIO images unavailable) |
