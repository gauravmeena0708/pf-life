# Demo script — EPFO platform POC (synthetic)

A guided walkthrough of the five journeys and the tier-2 freeze process, about 30 minutes. Every step here is
also exercised by an automated test (named in each section), so the demo and the tests cannot drift apart.

**Everything is synthetic.** No real person, establishment, UAN, bank account or EPFO rule. Amounts and
approval bands are illustrative (`config/demo-rules.yaml`).

## Before you start

```bash
make reset && make up && make migrate && make seed   # a clean stack with the full synthetic balances
make demo                                            # prints the URLs and personas
```

Open <http://localhost:5173>. Every persona's password is `Demo@2026!`. Switch persona from the account menu at
the top right; each switch is a real Keycloak sign-out and sign-in (never impersonation), and the portal always
asks for the password, so a shared computer never reuses the previous person's sign-in.

Every sensitive action asks for a **one-time code**. The code is shown on screen, clearly labelled as a
simulation; point out that the dialog says exactly what is being authorised (action, record, amount).

| Persona | Role | Used in |
|---|---|---|
| `emp-owner` | Establishment owner | A, D |
| `emp-preparer` | Payroll operator | A |
| `emp-signatory` | Authorised signatory | A, D |
| `member-a`, `member-b` | Members | A, B, C, D, E |
| `do-caseworker` | Dealing assistant (accounts) | B, D, freeze |
| `ro-ss`, `ro-ao`, `ro-apfc`, `ro-oic` | Section supervisor, accounts officer, APFC, officer in charge | B, freeze |
| `ro-cashier` | Cash section | B, D |
| `ro-pro` | Public relations officer | C |
| `zo-acc` | Zonal grievance officer | C |
| `zo-rpfc` | Zonal RPFC-I (freeze orders) | freeze |
| `caiu-investigator` | CAIU reviewer | D, E |
| `security-analyst` | Security operations | D |
| `auditor` | Audit division | C |
| `ho-policy` | ACC (HQ) — drafts rule changes | Policy |
| `ho-analyst` | CPFC — approves and publishes rule changes, dashboards | Policy |

---

## Journey A — Employer files and pays a monthly return (ECR)
*Test: `tests/e2e/test_journey_a_ecr.py`*

1. **`emp-owner` → Employer workspace.** Verify the establishment against the mock registry (PAN `AAAPD0000D`).
   Add the demo operator and authorise the demo signatory — each needs a one-time code.
2. **`emp-preparer` → Monthly returns (ECR).** *Load synthetic sample* → *Create and validate return*.
   Point out: every row is checked and every problem says what is wrong and how to fix it.
3. The operator tries to approve their own return → refused (separation of duties).
4. **`emp-signatory`** approves, then submits with a one-time code → a TRRN is issued. Retrying the same
   submission returns the same TRRN; a second challan is never created.
5. **`member-a` → My passbook:** "filed by employer, awaiting payment".
6. **`emp-signatory`** pays the challan through the mock bank → PAID → receipt.
7. **`member-a` → My passbook:** the contribution appears with employee and employer shares.
8. **`emp-owner`** revokes the operator → the operator's open browser is refused within 5 seconds.

## Journey B — A member's claim through the regional office
*Test: `tests/e2e/test_journey_b_claim.py`*

1. **`member-a` → My claims.** Choose *Advance for medical treatment*; the page shows the balance, the rule and
   the maximum. Enter ₹6,00,000 → review: plain-language summary, "how this will be decided"
   (DA → SS → APFC), rule version, ILLUSTRATIVE label → confirm with a one-time code.
2. **`member-b`** cannot open member A's claim (it simply does not exist for them).
3. **`do-caseworker` → Work queue → case.** Optionally *Get advisory analysis* (Journey E). Record the checks
   and recommend.
4. **`ro-ss`** approves (one-time code); **`ro-apfc`** gives the second approval. The same officer can never
   both recommend and approve.
5. **`ro-cashier`** pays — choose *Simulate bank return* to show the failure path — then re-issues.
6. **`member-a` → the claim:** the full timeline (officers by role, never by name), and *Profile & notices*:
   "Your claim … for ₹6,00,000 was paid into your bank account ending 0001."

## Journey C — Grievance and escalation
*Test: `tests/e2e/test_journey_c_grievance.py`*

1. **`member-a` → Grievances.** File one about the claim, attach a small text file.
2. **`member-b`** and an officer without grievance duties (`ro-apfc`) cannot read it.
3. **`ro-pro` → Work queue → grievance.** Note the advisory triage suggestion. Reply, link the claim as evidence.
4. **`member-a`** escalates → **`zo-acc`** takes it up and resolves it (one-time code).
5. **`zo-acc` → Grievance metrics**; **`auditor` → Audit log**: the hash chain is verified; click a
   correlation ID to see one request's events end to end.

## Journey D — Suspicious activity, recovery and revocation
*Test: `tests/e2e/test_journey_d_security.py`*

1. **`member-b` in a fresh browser window** (a new device) → *Account security* → change contact details →
   *My claims* → claim ₹1,000.
2. **`caiu-investigator` → Risk signals:** an advisory signal with a plain explanation and its evidence IDs.
   Point out: "take no action on this alone".
3. **`member-b`** confirms the claim → it goes to an officer instead of automatic approval, with the note
   "this is not an accusation". **`do-caseworker`** sees the advisory flag on the case.
4. Sign in as three different people in one browser (a kiosk) → *Shared devices (not signals)*.
5. **`caiu-investigator`** records *needs more evidence*, then *benign* — nothing is frozen, rejected or
   accused automatically.
6. **`member-b` → Account security → Request account recovery**; **`security-analyst` → Sessions & recovery**
   approves it (the verified contact details come back) and revokes the kiosk session.
7. **`emp-owner`** revokes the signatory → refused within 5 seconds.

## Journey E — The assistant (model off by default)
*Test: `tests/e2e/test_journey_e_assistant.py`*

1. **`member-b` → Ask the assistant:** "How much can I withdraw as a medical advance?" → a sourced answer,
   how sure it is, verified sources only.
2. Ask about someone else's UAN → refused.
3. Click *How long does a claim take? Community FAQ* → the planted document tries to take over the assistant;
   the page shows "Instructions ignored" and nothing is leaked.
4. **`do-caseworker`** → case → *Get advisory analysis*: structured, evidence IDs, "requires officer review";
   it cannot approve anything.
5. The model is off (`AI_PROVIDER=disabled`) — everything above still works. To try a local model:
   `AI_PROVIDER=ollama`, `docker compose --profile ai up -d`, `docker compose exec ollama ollama pull qwen2.5:0.5b`.

## Tier-2 process — freezing an account
*Tests: `tests/security/test_must_deny.py` (DENY-15, 22), `services/workflow-service/tests/test_process_engine.py`*

1. **`zo-rpfc` → Work queue → Start a process: Freeze of a member account.** UAN `100000000002`, category B,
   reason, order reference, one-time code.
2. **`member-b`** tries to file a claim → "This account is on hold".
3. **`do-caseworker`, `ro-ss`, `ro-apfc`, `ro-oic`** each verify in turn (the generic process screen, driven
   by `config/processes/member-freeze.yaml`). Out of turn → refused.
4. **`ro-oic`** de-freezes (only after a *genuine member* finding).

## Policy administration — changing rules without code
*Tests: `tests/e2e/test_policy_admin.py`, `services/platform-service/tests/test_policy_admin.py`*

1. **`ho-policy` → Rules and limits → Start a change.** Name it, choose *takes effect from* (for example the
   first of next month) and cite the notification.
2. Raise the EPS and EDLI wage ceilings from 15000 to 25000 → *Save and check*. Point out: every check is shown
   in plain words, *What changes* lists exactly two settings, and *Effect, with worked examples* shows that at
   ₹20,000 wages the employer's EPS goes from ₹1,250 to ₹1,666. *Submit for approval*.
3. **`ho-analyst` (CPFC)** opens it, approves with a one-time code → *Scheduled*. The drafter cannot approve
   their own change. A version that would silently undo a scheduled one is refused.
4. Returns for months before the date are still checked against ₹15,000; from that month, against ₹25,000.
   Every return and claim records the rule version it used.
5. Another change, in force today: add a claim type (for example *Advance for building a house*: 3 years of
   service, 90% of the balance, always decided by officers, its own chain DA → AO → APFC), or retire one, or
   change the default approval matrix and automatic-settlement limits. Members see it on *My claims*
   immediately; claims already made keep their rules; the assistant quotes the new figures.

## What the tests cover

```bash
make test         # unit tests of every service, the gateway and the shared packages
make e2e          # Journeys A–E on the running stack
make security     # the 25 must-deny tests of docs/permissions.md
make resilience   # broker down, consumer down, gateway restart (stops and starts containers)
```

Results of the last full run: `docs/test-report.md`.
