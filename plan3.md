# Plan 3 — Reliability, contract enforcement, and complete user journeys

**Reviewed:** 5 October 2026  
**Baseline:** `ccdc5ff`  
**Status:** Proposed implementation plan; the review itself changes only this document.

> Synthetic EPFO demonstration. Catalogue status, mocked integrations, test evidence, and illustrative policy must remain explicit. This plan makes no claim about current statutory requirements or production readiness.

## Assessment

The repository has substantial functional breadth. The next improvement cycle should make its existing behavior more dependable and easier to verify. Retain the gateway/BFF, separate domain ownership, integer-paise ledger, declarative processes, and existing event contracts. There is no evidence here that replacing this architecture would help.

Strengths already present:

- Generated catalogue, permissions, event schemas, and gateway routing; 539 distinct catalogue operations: **509 W, 24 M, 1 P, 5 ?**. Gateway method/path/status/owner values currently match the catalogue. These are declared implementation statuses, not 539 runtime verifications.
- Fresh-stack CI with isolated e2e, security, resilience, and UI jobs, migration checks, artifacts, and cross-service consistency checks.
- Producer event validation in checkout tests, inbox deduplication, per-aggregate consumer ordering within one process, and several out-of-order projection tests.
- Guided claim, bank-account, and transfer screens; shared accessible form controls; English/Hindi strings; visible-control claim lifecycle tests and generated manuals.
- ADRs and detailed slice history that explain design intent and known limitations.

The strongest remaining gaps are a concrete CSS error, event failure paths, database enforcement of documented invariants, HTTP contract drift prevention, and reporting that still reads baseline policy.

## Review evidence and limits

| Check performed | Result |
| --- | --- |
| `python3 -m pytest -q -p no:cacheprovider scripts/ci/tests scripts/manuals/tests scripts/lifecycles/tests` | **66 passed**; pytest warned that the async fixture loop scope is unspecified. |
| `python3 docs/tools/build_stakeholder_views.py --check` | Passed: 317 activities, 116 stakeholders, 3 without activities, no NEW endpoints, no catalogue endpoint without a caller. The three stakeholders should be classified intentionally, not automatically given activities. |
| Catalogue versus generated gateway operation keys/status/owner | Matched for all 539 operations; caller/upstream equivalence was not independently checked. |
| Focused consumer probe | Actual `Consumer._on_message()` with a fake message containing `[]` raised `AttributeError` without acknowledging or rejecting it. No live broker was involved. |
| `cd apps/web && npm run build` | Passed, but emitted an unmatched CSS brace warning and a large-chunk warning. Main JS: **1,534.20 kB minified / 396.58 kB gzip**. |
| Repository inspection | Reviewed ADRs, architecture, workflows, generators, shared event handling, ledger migration, workflow start/locks, reporting policy reads, frontend entry points, and representative journey tests. |

The review did not run the full business test suite, start/reset the Docker stack, inspect a current GitHub Actions run, or visually verify the app in a browser. The existing untracked `tests/e2e/test_representatives.py` was left untouched. Local checks used the available Python 3.13 / Node 24 environment; CI targets Python 3.12 / Node 22. Build-created changes to the tracked TypeScript cache were reverted.

A separate in-memory relay probe did not complete and was stopped. The relay rollback finding below is based on transaction control flow, not a passing integration reproduction.

`docs/test-report.md` contains useful dated evidence, including a 5 October result of 113/115 e2e tests on a used stack. Its description attributes the two failures to spent balances; that attribution was not reproduced in this review and is not a current green baseline.

## Priorities

Sizes describe relative scope, not delivery promises: **S** = focused repair; **M** = several related modules/checks; **L** = migration or broader journey work. Items can be delivered in separate reviewable changes.

| ID | Priority | Improvement | Size | Dependency |
| --- | --- | --- | --- | --- |
| P3.1 | Immediate | Repair stylesheet syntax and make syntax errors fail CI | S | None |
| P3.2 | High | Harden event rejection and outbox failure accounting | M | None |
| P3.3 | High | Enforce ledger immutability and unique active processes in PostgreSQL | L | None; start with reproductions |
| P3.4 | High | Read effective policy in reporting | S–M | None |
| P3.5 | High | Enforce catalogue → gateway → implementation → frontend contracts | L | Stage by domain |
| P3.6 | Medium | Align UI lifecycle evidence with guided journeys and isolate fixtures | L | P3.1 |
| P3.7 | Medium | Split frontend loading by route and contain request failures | M | P3.1; coordinate with P3.5 |
| P3.8 | Medium | Resolve lock/ordering guarantees and documentation drift | M | Findings from P3.2/P3.3/P3.5 |

## P3.1 — Repair the stylesheet and protect the build

**Evidence:** `apps/web/src/styles.css:491` opens `.pagination-buttons` and never closes it before the case-page rules begin. Vite reports `Expected "}" to go with "{"` but exits successfully. Subsequent selectors can be interpreted within the wrong scope. Browser impact still needs visual confirmation.

**Actions**

- [ ] Close the rule and inspect the work queue, case evidence/decision layout, and later stylesheet sections at desktop and narrow widths.
- [ ] Add a CSS syntax check to the web CI job. Keep formatting/style preferences separate from correctness checks so the initial change stays small.
- [ ] Preserve the EPFO navy/white theme, gold/red accents, formal typography, semantic structure, and readable focus states from `AGENTS.md`.

**Done when:** the build has no CSS syntax warnings; a deliberately malformed CSS fixture fails the chosen check; case and pagination layouts render correctly at 360px and desktop width.

## P3.2 — Make event failure behavior explicit

**Evidence:**

- `packages/common-persistence/epfo_persistence/consumer.py:67–80` catches JSON decoding failures, then calls `order_key` outside that handler. Valid JSON such as `null` or `[]` has no `.get`, so it raises before the retry/reject path. The `[]` case was reproduced with the actual consumer and a fake message; neither acknowledgement nor rejection occurred.
- `packages/common-persistence/epfo_persistence/relay.py:31–47` increments failed publish attempts inside `engine.begin()` and then re-raises. That transaction rolls back, including the diagnostic increment. Earlier successful publish markers in the same batch also roll back, making replay possible; inbox deduplication must remain intact.
- Event schema checks already exist in `epfo_persistence/contracts.py`; runtime images intentionally skip them when the schemas/dependency are absent. Producer test validation does not protect the consumer from every malformed broker message.

**Actions**

- [ ] Validate the envelope's object shape and required routing/identity fields before obtaining an ordering lock. Reject malformed messages into the dead-letter queue once, with a safe diagnostic reason.
- [ ] Give the relay module durable failure accounting without marking an unconfirmed publish as successful. Cover broker failure midway through a batch and recovery after publish-before-mark crashes.
- [ ] Expose pending outbox age, failure attempts, and dead-letter counts through the existing diagnostics path where practical.

**Done when:** invalid JSON, JSON scalars/arrays/null, and missing envelope fields cannot strand a delivery; healthy messages still progress; a failed publish leaves the row pending with a durable attempt count; re-delivery does not duplicate business effects. Use actual PostgreSQL/RabbitMQ integration checks for transaction and acknowledgement behavior.

**Architecture recommendation: Strong.** Deepen the existing delivery module: keep validation, acknowledgement, retry, and failure diagnostics behind its existing interface. The benefit is locality across all consumers. Extracting pass-through wrappers would not solve these failure paths.

## P3.3 — Prove and enforce database invariants

### Ledger immutability

**Evidence:** ADR-0003 promises an immutable journal. `services/contribution-service/migrations/versions/0002_contribution.py:22–32` enforces a unique business key and balanced lines, but its balance trigger handles INSERT/UPDATE/DELETE and does not itself prohibit balanced edits or deletion of all lines. No later append-only enforcement was found in the contribution migrations. This is a database enforcement gap; the review found no evidence of actual ledger corruption.

- [ ] Add PostgreSQL tests that attempt balanced historical edits/deletion and establish the current behavior.
- [ ] Enforce append-only journals and lines for the runtime writer through an appropriate migration and privileges/triggers. Keep corrections as new reversing journals.
- [ ] Distinguish migration/fixture ownership from runtime write authority; verify existing correction, reversal, settlement, and seeding paths before applying the restriction.

**Done when:** direct runtime-writer UPDATE/DELETE attempts fail, valid posting and reversal succeed, unbalanced posting still fails at commit, and duplicate business keys still cannot post twice.

### One active process per subject

**Evidence:** `services/workflow-service/app/engine/engine.py:343–346,371–385` checks for an open process then inserts a case. `app/infra/tables.py:56–64` has unique claim/grievance IDs but no corresponding active process/subject constraint. Two concurrent starts can pass the read before either insert commits. This is a concurrency risk identified statically, not a reproduced double-case incident.

- [ ] Reproduce concurrent starts using separate PostgreSQL sessions.
- [ ] Put serialization/uniqueness at the workflow module's persistence seam. Define active ownership explicitly because terminal states vary by YAML process.
- [ ] Preserve `_step`'s existing version-checked update and maker/checker rules.

**Done when:** simultaneous starts produce exactly one active case and one intended conflict/replay response, with one start event and no orphan lock; completing a process permits a valid later start.

**Architecture recommendation: Strong.** Keep process-start invariants inside the process module, rather than making every caller coordinate them. Preserve domain-specific process definitions under ADR-0005.

## P3.4 — Use effective policy consistently in reporting

**Evidence:** `services/reporting-service/app/api/dashboard_routes.py:52` reads the claim SLA from `baseline()`. `app/api/compliance_routes.py:38` does the same for filing due dates. Reporting already consumes published policy, and `epfo_persistence.policy.rules_on()` resolves an effective version; the documentation acknowledges these two remaining baseline reads.

- [ ] Resolve the policy appropriate to the report date and period, including historical due-date semantics, rather than silently using the initial configuration.
- [ ] Keep calculation inputs explicit within the reporting module and return the rule version used alongside report freshness.
- [ ] Test a changed settlement SLA, a changed filing due day, a future-effective version, and a historical report.

**Done when:** an applicable published change alters the affected report, a future change does not apply early, and historical evaluation follows documented effective-date semantics. Tests must distinguish baseline values from changed values.

## P3.5 — Close the HTTP contract and generation gaps

**Evidence:**

- `docs/architecture.md:112,121,204–205` describes implementation/schema comparison and generated frontend types. `.github/workflows/ci.yml` currently validates schema syntax and regenerated documents, without the described HTTP implementation comparison.
- `Makefile:64–68` does not invoke `apps/gateway/tools/build_routes.py` or include its output in the diff gate. The route file matches selected catalogue fields today, but this relationship is not enforced there.
- `apps/web/package.json` has no frontend contract generation command. `src/api/client.ts` and feature modules contain handwritten transport types; generic `api<T>` is a type assertion, not payload validation.
- Generated defaults in `docs/tools/build_gate0.py:434–441` leave resource data broadly typed unless an overlay supplies detail. Generating types alone will not repair underspecified contracts.

**Actions**

- [ ] Make one generation/check entry point cover contracts, permissions, gateway routes, and generated frontend data. Prefer a check mode that reports drift without rewriting the working tree; detect missing/untracked expected artifacts too.
- [ ] Compare implemented method/path operations and meaningful request/response schemas with the catalogue/overlays. Normalize path parameter names and gateway prefixes; account explicitly for engine-owned implementations, mocks, and planned 501 responses.
- [ ] Start with claims, contributions, and workflow decisions; tighten their overlays before generating frontend types. Expand domain by domain with explicit coverage tracking.
- [ ] Retain the current cookie, CSRF, representation, and step-up behavior in the transport adapter while adopting generated request/response types.
- [ ] Keep existing event contract tests; label HTTP and event verification separately.

**Done when:** a changed gateway caller/upstream/status, missing W operation, or incompatible implemented field fails CI; regenerated artifacts are deterministic; selected frontend callers fail compilation against an intentionally incompatible contract; P/? operations retain their documented behavior.

**Architecture recommendation: Strong.** A contract module should concentrate schema knowledge behind one generation/check interface. This implements ADR-0006; it does not require a new gateway architecture or a wholesale forms-library migration.

## P3.6 — Make journey evidence match the current UI

**Evidence:** `tests/e2e/test_claim_journey.py` already exercises the guided claim submission visibly, but uses API helpers for setup and settlement. The broader `tests/ui/claim_lifecycle.py:46–70` still submits through the older claim form. `scripts/ui_manuals.py` generates manuals from these UI suites. Existing axe checks disable color contrast in jsdom (`apps/web/src/features/P228f.a11y.test.tsx:25–28`).

- [ ] Move the lifecycle submission driver to `/member/claims/new` while preserving visible officer review, payment, member tracking, and balance assertions.
- [ ] Extend browser coverage to guided bank and transfer outcomes, OTP cancellation/retry, recoverable validation errors, and English/Hindi behavior.
- [ ] Keep API setup helpers explicitly identified. Require visible controls for the user actions a test/manual claims to demonstrate.
- [ ] Give mutable tests owned fixtures and bounded cleanup. Use the existing isolated stack capability for destructive suites; avoid settling another run's matching claim merely because amount/type match.
- [ ] Add browser contrast, keyboard/focus, 200% zoom, and narrow-layout checks for the shared journey shell and officer decision screen. Preserve existing jsdom accessibility coverage.
- [ ] Retire duplicate legacy forms only after lifecycle tests, navigation, and manuals use the guided replacements.

**Done when:** the selected full journey passes twice against its isolated fixture without balance exhaustion or leftover open claims; generated manuals show current screens; cancellation does not create a second draft; keyboard and Hindi journeys complete; baseline visual/accessibility results are attached to the change.

## P3.7 — Reduce initial frontend work and contain failures

**Evidence:** `apps/web/src/App.tsx` eagerly imports the broad feature set. The reviewed build emits a 1.53 MB main JS chunk. `src/api/client.ts:64–66` parses every nonempty response as JSON before mapping HTTP errors, so an HTML/plain-text proxy error escapes as a parsing error. Actual load time and rendered error behavior were not measured.

- [ ] Load major route groups on demand, starting with rarely visited officer/admin/exploration screens. Provide accessible loading and route error states.
- [ ] Measure JS transferred and navigation timings with a cold cache before and after. Set a documented initial-route budget from that baseline; keep the build's size warning visible.
- [ ] Map malformed/non-JSON error responses and network failures to a useful message while retaining correlation IDs when available. Do not automatically retry non-idempotent mutations.
- [ ] Add focused transport checks for empty success, JSON Problem Details, non-JSON failure, network error, and aborted requests.

**Done when:** the initial member route does not fetch unrelated officer/admin modules; the agreed bundle budget passes CI; lazy-load failures and unavailable gateway responses produce usable recovery options; existing CSRF, representation, and step-up tests remain green.

## P3.8 — Document guarantees that the implementation actually provides

**Evidence:** ADR-0004 describes Redis leases, heartbeat renewal, and database fencing. `services/workflow-service/app/api/locks_routes.py:48–52,63–93` instead stores database lock records and blocks on orphaned locks until supervised release. `epfo_persistence/consumer.py:52–80` serializes within one Consumer instance, while the relay uses `FOR UPDATE SKIP LOCKED`; neither alone establishes ordering across multiple replicas. The current local Compose topology does not justify assuming a multi-replica failure has occurred.

- [ ] Trace all protected writes and decide whether to implement ADR-0004 or record a superseding decision describing the supported POC lock behavior. Do not describe orphan-record visibility as stale-writer fencing.
- [ ] State the supported consumer/relay instance count and ordering scope. Add a multi-instance failure test before claiming horizontal scaling; choose a shared ordering strategy only if that topology is required.
- [ ] Reconcile `docs/architecture.md` with implemented packages, form handling, contract checks, and test environments. Mark intentions as planned until their checks exist.
- [ ] Add a short domain glossary/`CONTEXT.md` covering member versus account link, claim versus case, policy effective date, projection freshness, and representation. Link the relevant ADRs so future changes find the governing decisions.
- [ ] Put the latest verified commit, fixture provenance, suite counts, failures/skips, and artifact locations at the top of `docs/test-report.md`; retain dated history below. Generate headline counts where possible instead of copying stale totals into README.

**Done when:** every documented guarantee has an implementation/test pointer or an explicit limitation; a chosen fencing implementation rejects a stale writer in PostgreSQL, or a superseding ADR clearly states the narrower behavior; current local results and hosted CI results are distinguishable.

**Architecture recommendation: Worth exploring.** Lock semantics need a decision backed by the protected-write inventory. A Redis rewrite merely to match an old sentence is not justified; changing an accepted ADR must be explicit.

## Suggested delivery sequence

1. **Repair and reproduce:** P3.1; focused malformed-message and publish-failure reproductions from P3.2; PostgreSQL invariant reproductions from P3.3; reporting policy tests from P3.4.
2. **Correctness changes:** finish P3.2/P3.3/P3.4 with targeted regression checks and fresh-database migration verification.
3. **Prevent drift:** add gateway generation coverage and the first claims HTTP contract slice from P3.5, then expand by domain.
4. **Complete the demonstrated experience:** P3.6 and P3.7, with manuals and actual browser evidence regenerated after the UI changes.
5. **Record the verified result:** finish P3.8 and run the affected fresh-stack jobs on the final commit. Record failures as failures with context; never infer full-stack success from helper tests.

First delivery should be **P3.1 plus a focused P3.2 change**. Both have direct evidence, limited scope, and broad benefit. Subsequent database changes deserve separate review because they alter persistence guarantees. The product track below defines the next institutional milestone; its scenario specification can begin while the reliability work proceeds.

## Product milestone — Operate a miniature regional office for one simulated month

**Objective:** demonstrate a coherent institution in which members, employers, pensioners, officers, supervisors, accounts staff, and auditors can complete their work across a connected monthly operating cycle.

The repository already describes pensions, reconciliation, scrutiny, grievances, trust administration, member 360 views, notifications, and compliance in `docs/phase-2-plan.md` and `docs/endpoint-catalogue.md`. The proposals below extend and connect that coverage. They are proposed product work, not claims that the current implementation already satisfies the acceptance criteria.

Maintain the synthetic identity throughout the portal and its exports. Follow `AGENTS.md`: navy and white, restrained gold/red accents, formal readable typography, semantic layouts, accessible controls, and clear status language.

| ID | Product improvement | Priority | Main dependency |
| --- | --- | --- | --- |
| P3.9 | Realistic synthetic operating environment | First: defines the acceptance scenario | Existing seed/isolated-stack tooling; P3.2–P3.4 before relying on outcomes |
| P3.10 | Coherent stakeholder workspaces | Next, driven by scenario tasks | P3.9 scenario specification; coordinate with P3.6/P3.7 |
| P3.11 | Connected institutional records | Next | Existing member 360 and domain records; P3.5 for changed contracts |
| P3.12 | Consistent electronic case files | Next | P3.11; existing scrutiny, document, and audit flows |
| P3.13 | Supervisor's daily operations desk | After connected records | P3.11/P3.12; workflow authority and concurrency checks |
| P3.14 | Exception-resolution centre | After connected records | P3.11/P3.12; existing reconciliation and return flows |
| P3.15 | Consistent institutional documents | Alongside case files | P3.12; existing receipts, verification, and export paths |

### P3.9 — Build a realistic synthetic operating environment

- [ ] Define a configurable demo region with several offices, establishments, employment histories, pensioners, and outstanding cases. Start with a small deterministic fixture that runs on the supported local machine.
- [ ] Create named scenario snapshots with starting balances, policy versions, expected work, and expected outcomes. Record fixture provenance and restore only the selected isolated demonstration environment.
- [ ] Introduce a controlled business simulation clock for due dates, monthly processing, retirement, and delayed responses. Keep authentication expiry, cryptographic timestamps, and infrastructure timeouts on real time; distinguish simulated business dates from actual audit recording times.
- [ ] Advance scenarios through existing commands and events so their histories are explainable. Keep direct fixture initialization identifiable as setup.
- [ ] Provide a facilitator view for selecting scenarios, viewing prerequisites, and seeing the expected checkpoints. Label mock outcomes clearly.

**Done when:** the same monthly scenario can be restored and completed twice with matching business outcomes; no shared demonstration data is reset; advancing business time does not invalidate login sessions or fabricate previously completed decisions.

### P3.10 — Give each stakeholder a coherent workspace

- [ ] Organize member, employer, pensioner, officer, and supervisor homepages around pending actions, deadlines, recent outcomes, and the next useful task.
- [ ] Extend the existing life-event navigation and role menus. Use familiar actions such as “Pay this month's contribution,” “Respond to a clarification,” and “Review cases due today.”
- [ ] Put technical exploration, architecture views, and persona switching in an explicit demonstration mode. Preserve real authorization checks and the existing sign-out/sign-in behavior.
- [ ] Make status, empty states, validation, help, and English/Hindi terminology consistent across the selected monthly journeys.

**Done when:** each scenario participant can find and complete their assigned task from their homepage without knowing an endpoint, internal state code, or another role's navigation; role changes refresh the visible workspace and access correctly.

### P3.11 — Connect institutional records

- [ ] Extend the existing member 360 capability with linked member, establishment, and case records. Distinguish UAN, account link, claim, workflow case, payment reference, and grievance reference.
- [ ] Support navigation from employment to contributions, application, decision, payment, and related grievance without repeated identifier entry.
- [ ] Show the owning domain and freshness of copied facts, especially balances and payment status. Expose a useful pending-synchronization state when records have not converged.
- [ ] Apply purpose recording, jurisdiction, representation scopes, and field-level disclosure rules to linked views. Keep authoritative updates with the owning domain.

**Done when:** an authorized officer can reconstruct a scenario case from linked records; the member sees the permitted version of that history; an unrelated member or officer cannot gain access by following a link; conflicting or stale facts are visible rather than silently merged.

### P3.12 — Standardize the electronic case file

- [ ] Give claims, pensions, compliance, and grievances a recognizable file structure: application, evidence, scrutiny, correspondence, decisions, dispatch, and acknowledgement.
- [ ] Reuse existing dockets, attachments, timelines, and decision histories. Preserve each domain's required steps, approval bands, and maker/checker rules.
- [ ] Record evidence versions, the inputs considered, reasons, policy version, actor role, and decision time. Keep later corrections distinguishable from the record used for the original decision.
- [ ] Connect requests for clarification and applicant responses to the same file wherever the domain supports that lifecycle.

**Done when:** an authorized reviewer can explain what was requested, what evidence was considered, who acted, why the outcome followed, and what was communicated; later evidence changes do not rewrite the earlier decision record.

### P3.13 — Build the supervisor's daily operations desk

- [ ] Combine existing queues and reporting around unassigned work, aging cases, workload, approaching deadlines, and pending external responses.
- [ ] Support authorized reassignment and documented handover when officers are absent or transferred. Coordinate with existing HR posting and jurisdiction changes.
- [ ] Preserve approval authority and maker/checker restrictions after reassignment; require a recorded reason and audit trail.
- [ ] Make every count drill down to the cases behind it, with an as-of time and filters that explain the total.

**Done when:** a supervisor can identify a bottleneck, hand over eligible work, and verify its completion; reassignment neither loses a case nor grants an officer permission to approve their own earlier work; summary totals reconcile to the displayed case list.

### P3.14 — Create an exception-resolution centre

- [ ] Connect existing screens for returned payments, unmatched receipts, transfer discrepancies, missing documents, and identity conflicts through a common exception index.
- [ ] Give each exception an owner, reason, next action, age, related record, history, and closure evidence. Keep resolution commands in the appropriate domain.
- [ ] Distinguish waiting for the applicant, waiting for an external mock, and waiting for internal action. Surface the permitted explanation to the affected applicant.
- [ ] Prevent “resolved” from being a cosmetic flag: require the relevant correction, reconciliation, decision, or documented disposition.

**Done when:** each seeded exception can be followed from detection to an evidenced outcome; repeated notifications do not create duplicate work; reopening preserves the previous history; a bank return cannot appear as a successful payment merely because its task was closed.

### P3.15 — Make institutional documents consistent

- [ ] Inventory existing acknowledgements, receipts, notices, orders, statements, and correspondence before introducing templates.
- [ ] Standardize reference number, issuing office, date, subject, recorded authority, version, language, and verification details where applicable. Build on existing receipt verification.
- [ ] Bind an issued document to the data and decision version used to produce it. Define how a corrected document supersedes the earlier issue without silently replacing it.
- [ ] Provide readable print/PDF output with appropriate masking. Keep all demonstration documents and simulated signature/dispatch evidence clearly labelled synthetic.

**Done when:** the applicant can obtain the final record, an authorized reviewer can trace it to its case and decision, and verification distinguishes current, superseded, and invalid records where supported. Public verification must not expose additional personal details.

## Monthly operating scenario and product acceptance

Use this initial story to connect the product track:

1. An employer files a monthly return with errors, corrects it, obtains approval, and pays through the mock bank.
2. Contributions appear in the affected members' accounts and reconcile with the receipt and ledger.
3. One member changes jobs and completes a transfer; another submits a claim that encounters a bank return and follows the correction/re-payment path.
4. An officer is transferred while work is pending. An authorized supervisor records the handover, and the successor continues within the permitted approval chain.
5. A pension payment run includes a seeded exception; accounts staff resolve or explicitly carry it forward with an owner and reason.
6. A grievance links to one of these records and reaches a documented outcome communicated to the applicant.
7. At the end of the simulated month, the supervisor reviews workload and outstanding exceptions, accounts reconcile the selected monetary flows, and an auditor reconstructs a decision from its electronic file.

For every selected major journey, require all of the following:

- [ ] **Applicant:** understands eligibility, current progress, the next action, and the outcome; receives a useful final record.
- [ ] **Officer:** has the evidence and authority required for the decision, with reasons and policy version recorded.
- [ ] **Supervisor:** can identify delay and intervene through an authorized, traceable action.
- [ ] **Accounts:** can trace every monetary effect and reconcile it to its business cause and mock payment outcome.
- [ ] **Auditor:** can reconstruct the outcome from preserved records, including corrections and handovers.
- [ ] **Demonstrator:** can restore and rerun the scenario with known initial conditions and verified checkpoints.

**Product delivery order:** specify P3.9 first, then implement the smallest connected record/case-file slice (P3.11/P3.12) with its workspaces and documents (P3.10/P3.15). Add the supervisor and exception desks (P3.13/P3.14), and expand the operating scenario as each slice passes. Reuse the reliability gates in P3.1–P3.8 throughout. Completion means the simulated office can carry out this operating cycle with explainable outcomes and evidence for each role.
