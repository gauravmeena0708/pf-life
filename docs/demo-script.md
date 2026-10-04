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
| `ho-finance` | FA & CAO — annual interest crediting | Money |
| `member-c` | Member who left employment (final settlement, TDS) | Money |
| `pensioner-a`, `ro-pension` | Pensioner; APFC (Pension) who approves revisions | Money |
| `member-d` | Member with two member IDs (a previous job) | Exit and transfer |
| `ro-da-pension` | Dealing assistant (Pension) | Pension office |
| `member-e`, `ro-ss-pension`, `ndc-cpps` | Retired member; SS (Pension); CPPS operator | Pension settlement |
| `ro-fa-accounts` | Accounts wing (F&A) — views the Claim Approval Dockets | Claim tools |
| `claimant-a`, `ro-pro-counter` | Nominee of a deceased member; PRO counter (physical claims) | Death and EDLI claims |
| `ro-da-compliance` | Dealing assistant (Compliance) — OLRE scrutiny | The establishment record, changes and OLRE |
| `member-f` | Member whose Aadhaar is not verified yet | Member services (claim attestation) |
| `member-g` | Member who changed jobs (previous member ID still holds a balance) | Member services (auto-transfer) |
| `member-h` | Member in service since 2011 on wages above the ceiling | Higher pension |
| `worker-expat`, `iw-officer`, `ho-iwu` | International worker; International Workers cell; HO International Workers Unit | International workers |
| `ro-edli` | EDLI section officer | EDLI decision |
| `ho-publicity`, `ro-exemption` | HO Public Relations (circulars); exemption cell (trusts' monthly returns, surrendered trusts) | Public services, trusts |
| `exempted-trust`, `ho-exemption` | Demo Steel Works' PF trust; HO Exemption Division (ranking of all trusts) | Regulating the trust |
| `textile-trust`, `chemicals-trust` | PF trusts of Demo Textile Mills (surrenders) and Demo Chemicals (cancelled) | The trust's lifecycle |
| `auto-owner`, `member-ft`, `ho-finance` | Owner of Demo Auto Components; ARJUN DEMO, a first timer; FA & CAO | PMVBRY |
| `member-disabled` | SURESH DEMO, left Demo Engineering Works on permanent and total disablement | Disablement pension |
| `ro-eo`, `ro-rpfc2` | Enforcement Officer; RPFC-II (inquiries of 251–1,000 members) | An inspection and a 7A inquiry |
| `ro-legal` | Legal Cell (appeals, writs, prosecutions) | Appeals, membership disputes and prosecution |
| `ro-recovery`, `ho-compliance`, `ho-recovery` | Recovery Officer; HO Compliance Division; HO Recovery Division | Recovery of arrears |
| `zo-audit`, `ndc-is`, `zo-fraud`, `do-oic` | Concurrent Audit Cell; NDC IS Division; zonal fraud-risk committee; District Office in charge | Oversight and administration |

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
5. **`ro-cashier`** pays — choose *Simulate bank return* to show the failure path. The cashier cannot simply
   re-issue: **`member-a`** gives a new bank account on the claim (a mock penny-drop check; numbers ending 0000
   fail), **`ro-apfc`** approves the re-payment with a one-time code (adjudication is not reopened), and only then
   **`ro-cashier`** re-issues.
6. **`member-a` → the claim:** the full timeline (officers by role, never by name), and *Profile & notices*:
   "Your claim … for ₹6,00,000 was paid into your bank account ending 9012" (the corrected account).

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
4. **`ro-oic`** de-freezes (only after a *genuine member* finding). While frozen, open claims were *on hold*.
   After the de-freeze a claim that officers had already recommended restarts under the stricter
   after-de-freeze chain (for example DA → SS → APFC), its earlier approvals void; a claim frozen before any
   recommendation carries on, or is checked again if it had been approved automatically.

## Tier-2 process — Joint Declaration (member detail correction)
*Tests: `tests/e2e/test_joint_declaration.py`, `services/workflow-service/tests/test_joint_declaration.py`*

1. **`member-a` → Profile & notices → Correct my details.** Choose the detail (for example the name), the
   corrected value and the documents; submit.
2. **`emp-signatory`** attests it on the employer home (or returns it with a reason).
3. **`do-caseworker`** verifies; a minor correction is approved by **`ro-ao`**, a major one (name, date of birth)
   by **`ro-apfc`** with a one-time code. The profile shows the corrected value, the change history keeps the old
   one, and returns (ECR) are checked against the corrected record from then on.

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

## Date of exit and transfer (Form 13)
*Tests: `tests/e2e/test_exit_transfer.py`, `services/workflow-service/tests/test_exit_transfer.py`,
`services/member-service/tests/test_exits.py`, `services/contribution-service/tests/test_transfers.py`*

1. **`member-d` → View › Service History.** Two member IDs: AL-0008 at Demo Engineering Works (left in 2025, the
   employer never marked the exit) and AL-0009 (current).
2. **Manage › Mark Exit.** Choose AL-0008; the date must be in the month of the last contribution (Dec 2025) and
   is allowed two months after it; one-time code. It cannot be marked again, and no exit can be marked while
   another request is in progress.
3. **Online Services › One Member – One EPF Account.** Transfer AL-0008 into AL-0009 (one-time code).
4. **`emp-signatory` → Online Services › Transfer Claims** attests it (DSC / e-sign → one-time code).
5. **`do-caseworker`** verifies it from the work queue; **`ro-ao`** approves (one-time code). The ledger moves
   the whole balance; both passbooks show it (*Transferred out* / *Transferred in*).
6. **`member-d` → Recent applications → Annexure K**: the transfer statement.
7. Employer side: **`emp-preparer` → Member › Member Profile** marks a member's date of exit; it takes effect
   only when **`emp-signatory`** approves it under **Member › Approvals**.

## Registering a joinee and approving KYC
*Tests: `tests/e2e/test_registration_kyc.py`, `services/member-service/tests/test_onboarding.py`*

1. **`emp-preparer` → Member › Register-Individual.** Name, date of birth, gender, Aadhaar (checked by a mock
   UIDAI; a number ending 0000 fails), mobile, date of joining → a new UAN and member ID. With *Existing UAN*, a
   new member ID under that UAN (name and date of birth must match). Then **Form 11**. The joinee is in the ECR
   member list at once; *Dashboards › Active Members* downloads the list as CSV; *Missing details* fills only
   what the record lacks.
2. **`member-d` → Manage › KYC.** Add a bank account (mock penny-drop) or a PAN (mock NSDL; an individual PAN has P
   as the fourth letter) with a one-time code → *waiting for your employer's approval*.
3. **`emp-signatory` → Member › Approve KYC …** approves with DSC / e-sign (one-time code). The member's KYC,
   bank for payments and *Ready to claim?* change; a verified PAN lowers TDS on a taxable withdrawal.
4. *KYC Bulk* uploads many lines at once and lists the lines it could not accept.

## Pension office and pensioner services
*Tests: `tests/e2e/test_pension_services.py`, `services/pension-service/tests/test_pensioner_services.py`*

1. **`ro-pension` (APFC Pension) → Pension › Life certificates overdue.** PPO-DEMO-0002's certificate lapsed on
   31 August → *Suspend* (reason, one-time code). Resuming without a certificate is refused.
2. **`ro-da-pension` → Pension office › Initiate an activity**: *Physical life certificate (PRO)* for
   PPO-DEMO-0002 (one-time code). The DA cannot settle it.
3. **`ro-pension`** settles it in the tracker: the certificate is valid for a year, the pension resumes and the
   months held back are credited that day. *Pension Enquiry Details* shows the eight tabs.
4. **`pensioner-a` → Services**: submit a Digital Life Certificate (mock Jeevan Pramaan), print the PPO, see a
   pension slip, ask to change the bank account (the APFC settles it) and make a declaration.
5. **Public services → Pension enquiries** (no login; answer the one-use question): Know your PPO, pension
   status, payment enquiry (months only, no amounts), life certificate.

## Pension settlement: Form 10D to a pension in payment
*Tests: `tests/e2e/test_pension_settlement.py`, `services/pension-service/tests/test_settlement.py`*

1. **`member-e` → Online Services › Pension (Form 10D).** Retired on 31 January 2026 after 15 years 5 months:
   *Apply* → pension from 1 February, estimated ₹3,214 a month (₹15,000 × 15 / 70).
2. **`do-caseworker`** prepares the Input Data Sheet; **`ro-ao`** approves it (one-time code).
3. **`ro-da-pension`** generates the worksheet (the formula in force when the pension starts; past service from a
   cancelled scheme certificate can be added first); **`ro-pension`** approves it.
4. **`ro-da-pension`** issues the PPO and proposes the initial arrear (February to last month); **`ro-ss-pension`**
   checks it; **`ro-pension`** e-signs the PPO (one-time code bound to the arrear); **`ro-da-pension`** dispatches.
   The member sees each desk; the pension is in payment and the arrear credited.
5. **`ndc-cpps` → CPPS disbursement**: run last month, then *Reconcile* (the mock sponsor bank answers; accounts
   ending 0000 are returned). **`ro-pension`** prepares the Bank Reconciliation Statement.

## Claim tools: withdrawal, CAD, payment scroll, member 360
*Tests: `tests/e2e/test_claim_lifecycle.py`, `services/claim-service/tests/test_lifecycle.py`*

1. **`member-a` → a claim under review → Documents and withdrawal**: upload a PDF, then *Withdraw this claim*
   (one-time code). It closes in the work queue too. After an approving officer decides, withdrawal is refused.
2. **`ro-fa-accounts` → Claims & settlement › Claim Approval Docket (CAD)**: enter a claim's ID → each level's docket
   (gross, interest included, TDS, net, rule and static-data versions).
3. **`ro-cashier` → Payment scroll**: see the claims ready, send them to the bank in one scroll (one-time code
   bound to the total; *simulate bank return* to show the failure path), then *Reconcile returns*.
4. **`do-caseworker` → Members › Member**: the member 360 view needs a purpose, which the audit log keeps;
   *Inoperative accounts*; *Claim audit trail* with the forms filed with the claim.

## Death and EDLI claims; the PRO counter
*Tests: `tests/e2e/test_death_claims.py`, `services/claim-service/tests/test_death_claims.py`*

1. **`claimant-a` → Death claims › PF claim (Form 20)**: UAN 100000000901 (pre-filled), one-time code. The claim
   shows the two nominees and their shares. *Add a co-beneficiary* adds a legal heir with no share.
2. **`ro-apfc` → Claims & settlement › Death claims: beneficiary shares**: enter the claim ID; amend a share with a
   reason (court order, share settled earlier, …; one-time code). Payment is held until shares total 100 %.
3. **`do-caseworker` recommends, `ro-ao` approves, `ro-cashier` pays**, as for any claim. The shares table then
   shows what each beneficiary was paid.
4. **`claimant-a` → EDLI claim (Form 5IF)**: the amount is worked out from the published EDLI rules and paid from
   the EDLI fund.
5. **`ro-pro-counter` → PRO counter**: inward a Form 19 for UAN 100000000002 and validate the filer (BHARAT DEMO,
   2 Nov 1985); inward a *physical life certificate* for PPO-DEMO-0001 — `ro-da-pension` sees it as NEW on the
   updation tracker.

## Ledger locks, signed Form 13, establishment freeze, Annexure K
*Tests: `tests/e2e/test_ledger_and_establishment.py`, `services/workflow-service/tests/test_locks_and_freeze.py`*

1. **`ro-oic` → Members › Ledger locks**: UAN 100000000005 shows a lock left by a dead annual-accounts batch
   (orphaned). Release it with a reason (one-time code). While it stood, officers' decisions on that member were
   refused with "Unable to lock the member's ledger".
2. **Form 13 (see "Date of exit and transfer")**: after the employer attests, the DA's case page lists the
   *Employer-signed Form 13*; *Verify* is refused until the DA has opened it.
3. **`zo-rpfc` → Work queue › Freeze of an establishment**: EST-DEMO-0001, category B, order reference. `emp-owner`
   sees the freeze banner and cannot approve an ECR. **`ro-apfc`** recommends the de-freeze, **`ro-oic`** orders it.
4. **`do-caseworker` → Claims & settlement › ANNEXURE K FILE**: list inward / outward files; reconcile one against
   the transfer and member records, and against a VDR receipt (one-time code each).

## Claim scrutiny as in the CITES manuals: docket, recommendation, rejection, stop
*Tests: `tests/e2e/test_cites_claim_rules.py`, `services/workflow-service/tests/test_cases_api.py`*

1. **`member-a`** files an advance of ₹1,50,000 (DA → AO).
2. **`do-caseworker` → the case**: *Stop claim processing* with a reason — the claim moves to *Stopped claims* on
   the work queue; *Restart claim* brings it back. *Generate docket* (Claim Approval Docket), then choose *Recommend
   to Approve* or *to Reject* and the account status; confirm with the one-time code.
3. **`ro-ao` → the case**: generate the docket; the options follow the recommendation — after "approve" only
   *Approve* or *Send back to first level*. Send it back; the DA re-forwards it as *Recommend to Reject*; the AO
   now sees *Reject*. At a middle level (a larger claim: DA → SS → APFC) *Recommend to Reject* returns it to the DA.
4. **`ro-fa-accounts` → Claim Approval Docket**: every level's version of the docket.

## The establishment record, changes and OLRE
*Tests: `tests/e2e/test_establishment.py`, `services/employer-service/tests/test_establishment.py`*

1. **`emp-owner` → Establishment › Establishment KYC and bank accounts**: verify a TAN (`DELD12345A`; one containing
   `00000` is not found in the mock registry). *Branches (Form 2A)*: add a department. *Form 5A*: file the
   ownership return (one-time code for DSC / e-sign). *Contractors*: link one with its work order.
2. **Establishment Profile**: ask for an address change — it becomes a request, the record does not change yet.
3. **`ro-apfc` → Establishments & compliance › Establishment change requests**: approve it; the owner's
   configuration now shows the new address.
4. **OLRE**: `emp-owner` registers a new establishment (PAN `AAAFD1234K`); **`ro-da-compliance`** views its
   documents and records scrutiny (compliance e-file); **`ro-apfc`** decides coverage.

## DSC / e-sign registration, pending approvals, family pension
*Tests: `tests/e2e/test_signatures_family_pension.py`, `services/employer-service/tests/test_signatures.py`,
`services/pension-service/tests/test_settlement.py`*

1. **`emp-owner` → Establishment › Authorized eSign List**: register the signatory's DSC (one-time code), then
   upload the signed request letter (PDF).
2. **`ro-apfc` → OLRE › DSC / e-sign registrations**: approve it. After a signatory is revoked, the revoke letter
   comes here too.
3. **`emp-signatory` → Member › Approvals**: *Pending approvals* lists what waits for the signature (e.g. a Form 13
   to attest).
4. **`claimant-a` → Family pension (Form 10D)**: file for GANESH DEMO (UAN 100000000901); the estimate is 50% of
   his formula pension. **`do-caseworker`** sees it under *Form 10D pension claims* and it runs desk by desk as in
   "Pension settlement"; the PPO is issued in the widow's name.

## Arrear and supplementary returns, cancelling a TRRN, 14B / 7Q
*Tests: `tests/e2e/test_returns_and_demands.py`, `services/contribution-service/tests/test_returns.py`*

1. After Journey A, **`emp-preparer` → Payments › ECR Upload**: choose *Arrear* for the month just paid (a member of
   that return, arrear wages) or *Supplementary* (a member left out). Before the regular return is paid both are
   refused.
2. **`emp-signatory`**: approve and submit it, then *Cancel TRRN* (one-time code) — the wage month is free again.
3. **Payments › Return monthly dashboard**: each month, its returns, due date and whether it was paid late.
   *Demands*: 14B damages and 7Q interest raised by the late payment. *Direct Challan*: fill from the open demands,
   raise the challan, pay it on the ECR page.
4. **`ro-da-compliance` → Returns office**: knock the demands off against the paid challan; **`ro-ss`** approves.
5. **`ro-cashier`**: pay a challan with the scenario *Stuck at the bank*, then *Reject stuck payment* here; the
   employer can pay again. **`do-caseworker`** can reject a submitted, unpaid return.

## Receipts, reversals, recredits and Appendix E
*Tests: `tests/e2e/test_ledger_office.py`, `services/contribution-service/tests/test_ledger_work.py`*

1. Submit a return without paying it. **`ro-cashier` → Receipts and ledger**: record a cheque for its amount.
2. **`do-caseworker`**: allocate the receipt to the TRRN — the return posts; the employer can no longer pay it
   online. A receipt with nothing allocated can be rejected (dishonoured cheque).
3. **Reverse a posted journal / recredit a transfer**: reverse a contribution, or recredit a Form 13 transfer.
4. **Appendix E**: the DA proposes *Transfer of 1.16% from employer share to EPS* for member A with the notesheet;
   **`ro-apfc`** approves; member A's passbook shows the adjustment.

## Form 10C withdrawal benefit; annual statement
*Tests: `tests/e2e/test_pension_withdrawal_statement.py`, `services/claim-service/tests/test_tds.py`,
`services/contribution-service/tests/test_statements.py`*

1. **`member-c` (FARAH DEMO, left on 30 June 2026 after 3 years 5 months) → Online Services › Claim**: *Pension
   withdrawal benefit (Form 10C)* shows ₹46,500 (Table D factor 3.10 × ₹15,000, illustrative). File and confirm.
2. **`do-caseworker`** recommends, **`ro-ss`** approves (each generates the Claim Approval Docket), **`ro-cashier`**
   pays: the money comes from the EPS fund, not her PF balance.
3. **`member-a` → View › Annual statement and taxable interest**: opening, the year's movements and the closing
   balance per member ID; the taxable part of the interest (none below ₹2,50,000 of own contributions a year).

## Primary member ID
*Tests: `tests/e2e/test_primary_member_id.py`, `services/*/tests/test_primary_member_id.py`*

1. **`member-d` → View › Service History**: AL-0009 is marked **P** (the latest member ID with contributions);
   AL-0008 is secondary. On the claim screen AL-0008's claims are refused: "Requested member ID does not match with
   the primary member ID (AL-0009)". The transfer form offers only AL-0009 as the target.
2. **`member-b` → Claim**: *Final settlement* lists "All services are not transferred to the primary member ID:
   AL-0903 holds ₹50,000" — AL-0903 is on BHARAT's older UAN, linked by the same verified Aadhaar.
3. **`do-caseworker` → Member 360** for UAN 100000000903: the Aadhaar-verified set and its primary member ID.

## Oversight and administration
*Tests: `tests/e2e/test_oversight_administration.py` and the unit tests of audit-, platform-, workflow-, member- and
reporting-service*

1. **`security-analyst` → Security › Incidents**: record a HIGH unauthorised-access incident detected an hour ago;
   it is reported to CERT-In (mock) within the 6-hour window, with an acknowledgement number.
2. **`zo-audit` → Concurrent audit**: today's extract lists the day's settlements, adjustments and transfers with red
   flags; *Raise alert* to RO-DEMO-01. **`ro-oic`** replies (within 3 days, else marked late).
3. **`ro-oic` → Issue Tracker**: raise a freeze for UAN 100000000909 with the order; **`ndc-is`** executes it (one-time
   code); the member 360 view shows the account frozen; de-freeze the same way. A *login notice* for member A reaches
   her notifications.
4. **`zo-fraud` → Fraud-risk cases**: the zone's claims with risk signals and account freezes.
5. **`hrm-employee` → Postings**: post `ro-pro-counter` to RO-DEMO-02 and back; each service follows.
6. **`do-oic` → District dashboard**; **`emp-owner` → Home**: the establishment dashboard with alerts;
   **`emp-preparer` → Member › Location mapping**: map member A to branch BR-01.

## Public services, grievances, circulars, the interest rate, surrendered trusts
*Tests: `tests/e2e/test_public_services.py` and the unit tests of grievance-, intelligence-, claim-, reporting-,
contribution- and platform-service*

1. **Public page (no login)**: *Grievance without login* — name, mobile, the demo question and any six-digit code;
   note the registration number. *Grievance status* with it and the mobile. *Claim status* with a claim number and
   UAN. *Circulars*: filter by category; open one and its versions. *Establishments* → *e-Report Card*.
2. **`member-a` → Grievances**: *Send a reminder* (once a day); after the office resolves it, *Feedback* (satisfied
   closes it). **`ro-pro`** can *Transfer to another office* (RO-DEMO-02); it leaves the queue.
3. **`ho-publicity` → Circulars**: publish one, then publish the same number again: version 2, version 1 superseded.
4. **`ho-finance` → Record the interest rate** for 2026-27 (CBT date, Ministry concurrence; one-time code bound to
   the rate). **`ho-policy` → Policy**: a draft rule set with that rate is waiting; submit it; **`ho-analyst`**
   publishes it.
5. **`ro-exemption` → Surrendered trusts**: EST-DEMO-0003, a transfer reference and the trust's member lines;
   the total is confirmed with a one-time code; each line is posted to the member's ID at the trust.

## Higher pension, international workers, the EDLI decision
*Tests: `tests/e2e/test_higher_pension_international_edli.py`, `services/pension-service/tests/test_higher_pension.py`,
`services/international-service/tests/test_international.py`, `services/claim-service/tests/test_edli_decision.py`*

1. **`member-h` → Pension on higher wages**: opt from September 2014 with the declaration and consent (one-time code).
   `member-a` is refused: not in service on 1 September 2014.
2. **`emp-signatory` → Higher-pension joint-option validation**: paste the wages (`2015-01,40000` per line), *Preview
   dues* (8.33% of the wages above ₹15,000), then *Validate*. `member-h` sees the dues and the month-by-month working.
3. **`emp-signatory` → International workers (CoC)**: apply for a worker posted to Germany (from the agreement
   catalogue), upload the signed PDF; **`iw-officer`** issues it; the employer downloads the certificate and extends
   it by six months. **`ho-iwu`** reads the agreements; **`worker-expat`** sees their coverage (no agreement with
   their country: full wages, no ceiling).
4. **Death claims**: after the officers admit the Form 5IF claim, **`ro-edli` → EDLI claims** enters the verified
   average wages, works out the benefit and sanctions it (one-time code bound to the amount).

## Tax certificates, UAN allotment and inoperative accounts
*Tests: `tests/e2e/test_small_member_tax_inoperative.py`, `services/*/tests/test_tds_documents.py`, `test_inoperative*.py`*

1. **`member-a` → My claims › TDS certificate (Form 16A)**: pick the year; tax deducted by quarter, illustrative.
   **`do-caseworker` → Claim tools › Quarterly TDS statement**: file Q1 of 2026-27 (mock acknowledgement); filing it
   again is refused with the acknowledgement.
2. **`csc-operator` → UAN allotment**: enter a person's details, *Capture face (mock)*, submit — a new UAN; the same
   Aadhaar again is refused with the masked UAN. **`member-a` → Security › Activate your UAN** with OTP 123456.
3. **Public › Inoperative account search** (no login): MOHAN DEMO, 14-02-1970, "textiles" — a masked match, no
   balance; the demo OTP shows ₹2,00,000 and what to do next.
4. **`do-caseworker` → Claim tools › Inoperative accounts**: *Verify through co-workers* with UANs 100000000004 and
   100000000906 (one alone is refused). **`ro-ao`** reactivates it (one-time code bound to the balance); it leaves the
   list.

## Coverage, closure, office transfer and contractors
*Tests: `tests/e2e/test_small_employer_lifecycle.py`, `services/employer-service/tests/test_lifecycle_feeds.py`*

1. **`emp-signatory` → Establishment › Coverage, closure and office**: voluntary coverage for 25 employees is refused
   (covered compulsorily); for 12 with 8 consenting it goes to the office; ask for closure and for a transfer to
   RO-DEMO-02 (one-time codes). **`ro-apfc` → OLRE / change requests** sees all three with their details and decides.
2. **`emp-preparer` → ECR**: on a submitted return, *Tag workers to a principal employer* (EST-DEMO-0002, work order
   WO/DEW/2026/014) and tick the workers.
3. **`principal-owner` → Establishment › Contractors › Compliance**: the demo establishment's months for the tagged
   workers — members, wages, contribution — and the unpaid ones highlighted.

## Pension office: higher-pension dues, Special 10D, disbursement lists, actuarial extract
*Tests: `tests/e2e/test_small_pension_office.py`, `services/pension-service/tests/test_p2_12c.py`*

1. **`ro-pension` → Pension office › Higher pension**: approve member H's validated option (one-time code bound to
   the dues). **`do-caseworker` → Claim tools › Higher pension dues transfer**: move the dues; member H's passbook
   shows the transfer to the pension fund and the option reads *dues transferred*.
2. **`ro-da-pension` → Special 10D case**: MOHAN DEMO, service before 2002 and wages missing, an employer certificate.
3. **`ro-pension-disbursement` → Disbursement lists**: last month's pensions by bank, with totals; print.
4. **`ho-actuarial` → Actuarial extract**: pseudonymous rows and aggregates; download CSV — no names or numbers that
   identify anyone.

## Internal audit, personal-data requests and RTI
*Tests: `tests/e2e/test_small_oversight.py`, `services/audit-service/tests/test_internal_privacy.py`, `services/grievance-service/tests/test_oversight.py`*

1. **`zo-internal-audit` → Internal audit**: a report on RO-DEMO-01 and a para (claims, ₹50,000 at risk).
   **`ro-oic` → Audit paras**: reply and ask for the para to be dropped. **`auditor`** (Audit Division) drops it
   (one-time code).
2. **`member-a` → Security › Your personal data**: ask for access. **`ho-dpo` → Data-principal requests**: a refusal
   without its legal basis is not accepted; answer it; the member sees the answer.
3. **`ro-pro` → RTI applications**: an application with neither fee nor BPL card is refused; register it with the
   fee — reply due in 30 days; a refusal must cite its section; reply with the information.

## Head office reporting: balance sheet, investments, board packs
*Tests: `tests/e2e/test_small_ho_reporting.py`*

1. **`statutory-auditor` → Balance sheet**: the funds' liabilities against the assets held, from the ledger; it balances.
2. **`ho-investment` → Investments**: the quarter's positions by fund and asset class against the pattern of
   investment (illustrative bands); anything outside its band is flagged.
3. **`cbt-member` / `fiac-member` → Board packs**: contributions, claims, grievances and investments in aggregate —
   no personal data; FIAC's pack adds the pattern flags.

## Members of an exempted establishment (PF with its trust)
*Tests: `tests/e2e/test_exempted_members.py`, `services/*/tests/test_exempted*.py`*

1. **`member-p` → Passbook**: her member ID at Demo Steel Works shows the PF *as reported by the trust* with the time
   fetched; the pension (EPS) service is with EPFO. **My claims**: a final settlement on that ID says the trust settles
   it within 20 days.
2. **`member-p` → Service › Transfer**: move her earlier EPFO member ID into the trust; `steel-signatory` attests,
   `do-caseworker` verifies, `ro-ao` approves. *Transfer status*: PF — sent to the trust; Pension — completed.
3. **`member-r`**: move his PF out of the trust; once approved, *Transfer status* shows PF — waiting for the trust and
   Pension — waiting for the PF. **`exempted-trust` → Trust**: the Annexure K request; submit the amount, the service
   and 2 months of breaks. **`do-caseworker` → Claim tools › Annexure K from exempted trusts**: reconcile it with the
   receipt (one-time code). Both legs now read *completed* — the pension one started by itself — and the pension
   estimate shows his trust spell with its breaks.

## Regulating the trust: monthly return, evaluator, priority matrix
*Tests: `tests/e2e/test_trust_regulation.py`, `services/contribution-service/tests/test_exempted_returns.py`*

1. **`exempted-trust` → Trust › Monthly return**: file September 2026 — the employee figures must balance (the check is
   shown as you type), the due is the two shares, a transfer on time. *Returns filed* shows 600 of 600 and no flags;
   July shows a lower score, its transfer 7 days late and claims settled late (category A).
2. **`ro-exemption` → Exempted establishments**: the ranking for July; open Demo Steel Works, its returns and flags; on
   the late-claims flag, record a *show-cause notice* with a one-time code (advice is not offered for category A).
3. **`ho-exemption`**: the ranking across all offices, read-only.

## The trust's lifecycle: annual audit, surrender, cancellation
*Tests: `tests/e2e/test_exemption_lifecycle.py`, `services/employer-service/tests/test_exemption_lifecycle.py`,
`services/*/tests/test_exemption_end.py`*

1. **`exempted-trust` → Trust › Annual audited accounts**: 2025-26, the corpus movement adds up as you type; a qualified
   opinion needs observations. **`ro-exemption`**: the trust's audits, the qualified one marked.
2. **`textile-trust` → Surrender the exemption (Form SE-1)**: a date at least 30 days ahead, the trustees' resolution, the
   undertaking and consent; one-time code. The proceeding shows who acts next and by when.
3. **`ro-oic` → Exemption proceedings**: permit compliance as un-exempted (SE-5). The trust's profile now shows the end
   date; **`ro-exemption` → Past accumulation ingestion** credits NEHA DEMO's PF (AL-0921).
4. **`ro-exemption`** sends the agenda (SE-2); **`zo-acc`** forwards it to HO (SE-3); **`ho-exemption`** records the EEC,
   the CBT, the reference to the Government and its notification; **`ro-exemption`** records the gazette notification.
   The exemption reads *surrendered*.
5. **`ro-exemption` → Exempted establishments**: on Demo Chemicals, open cancellation — a show-cause notice (CE-1) on
   Condition 25. **`chemicals-trust`** replies, admitting and relinquishing; **`ro-oic`** takes it over at once; the
   same route up ends in *cancelled*, and the trust's monthly returns are refused from then.

## PMVBRY — the employment-linked incentive
*Tests: `tests/e2e/test_pmvbry.py`, `services/contribution-service/tests/test_pmvbry.py`*

1. **`auto-owner` → PMVBRY**: Demo Auto Components — baseline 30 (Aug 2024 – Jul 2025), threshold 2, crossed in
   October 2025, 48 months as a manufacturer. October: 33 employees but only 2 additional count (one joiner left before
   six months). Exercise the option with the GSTN and the PAN-linked account (one-time code); the cycles show what is due.
2. **`member-ft` → PMVBRY**: ARJUN DEMO, first job from 3 October 2025 at ₹14,000: instalment 1 of ₹7,000 after six
   months; instalment 2 of ₹7,000 after twelve months once he completes the financial literacy course on the page.
3. **`ho-finance` → PMVBRY**: preview September 2026 — first-timer instalments and the employer's cycle; one first
   timer's ₹6,000 is *held* (bank account not Aadhaar-seeded). Pay with a one-time code bound to the amount; a second
   preview shows nothing left. **`ho-analyst`** (CPFC) sees the dashboard.

## SMS and e-mail
*Tests: `tests/e2e/test_notifications.py`, `services/member-service/tests/test_notification_delivery.py`*

1. **`member-ft` → Account security › SMS and e-mail**: SMS and e-mail on, English or हिन्दी; the essential messages
   that always go by SMS are listed.
2. **`member-ft` → Grievances**: register one. Under the notice: *SMS to ******0914 · Delivered*; *E-mail to
   a\*\*\*@bounce.invalid · Failed: BOUNCED*.
3. **`ro-pro` → SMS / e-mail deliveries**: the failed e-mail with each attempt (time, HTTP 422, BOUNCED); *Send again*
   once the member's e-mail is corrected. **`ndc-is`** sees the gateway's deliveries across offices.

## An inspection and a 7A inquiry
*Tests: `tests/e2e/test_inquiry_7a.py`, `services/compliance-service/tests/test_proceedings.py`*

1. **`ro-apfc` → Inspections and 7A inquiries**: schedule an inspection of EST-DEMO-0001 on a workers' complaint.
2. **`ro-eo`**: report — 40 employees found, 12 not enrolled, dues estimated at ₹50,000; recommend a 7A inquiry.
3. **`ro-da-compliance`**, then **`ro-ss`**: put the report up (each step shows its due date); **`ro-apfc`** decides
   to initiate. **`ro-ss`** registers it: a diary number, and with 40 contributory UANs it goes to an APFC.
4. **`ro-apfc`**: open the inquiry; issue summons (one-time code) — the hearing is virtual; record the daily order;
   **`emp-owner` → Inquiries (e-Proceedings)** sees the summons and the link, and replies; record the last hearing as
   concluded (the order is due in 15 working days).
5. **`ro-apfc`**: pass the 7A order — dues by account and month, a one-time code for the amount. The order appears to
   the employer, and the dues as a demand payable by a direct challan.

## Damages, interest, review and scrutiny
*Tests: `tests/e2e/test_proceedings_b.py`, `services/compliance-service/tests/test_proceedings_b.py`*

1. Pay a return late (as in *Compliance*): 14B damages and 7Q interest are worked out automatically.
2. **`ro-da-compliance` → Inspections and 7A inquiries › Damages notice**: draft it for EST-DEMO-0001 — it covers the open
   14B / 7Q demands. **`ro-ss`** endorses, **`ro-apfc`** approves: a diary number, allotted by size.
3. **`ro-apfc`**: notice and hearing as for 7A; pass the 14B order (reduce it, giving the reasons) and the 7Q order (the
   statutory amount). The employer's demands show the ordered amounts in place of the automatic ones.
4. After a 7A order: **`emp-owner` → Inquiries** applies for a review on new evidence. **`ro-apfc`** records the RPFC-II's
   view, grants it, hears again and passes the order under review — the demand is replaced. On an ex-parte order the
   employer can apply to set it aside instead; the officer can also reopen a case under 7C.
5. **`ro-rpfc2` → Scrutiny of orders**: the APFC's order of this month, due by the 15th of next month; record the
   observations. **`zo-acc`** scrutinises the RPFC-I's orders.

## Appeals, membership disputes and prosecution
*Tests: `tests/e2e/test_proceedings_c.py`, `services/compliance-service/tests/test_proceedings_c.py`*

1. **`ro-ss` → Membership dispute (Para 26B)**: two employees, one-time code — allotted to the RPFC-II. **`ro-rpfc2`**:
   notice, hearing, the order — one a member from January 2025, the other not eligible.
2. After a 7A order: **`ro-legal` → Legal cases › Register an appeal**: the Tribunal case number; the pre-deposit due is
   75% of the dues. Record the deposit — now it can be heard. Record the Tribunal's order *remanded*: the case goes back,
   to the RPFC-II this time. The employer can no longer seek a 7B review of that order.
3. **`ro-apfc` → Prosecutions**: a show-cause notice for returns not filed. **`emp-owner` → Inquiries** replies. **`ro-oic`**
   sanctions; **`ro-eo`** records the complaint filed in court; **`ro-legal`** records the conviction.

## Recovery of arrears
*Tests: `tests/e2e/test_recovery.py`, `services/compliance-service/tests/test_recovery.py`*

1. **`ho-analyst` → PMVBRY**: Demo Engineering Works is excluded — its 7A order (June 2026) is not complied with.
2. **`ro-apfc` → Inspections and 7A inquiries**: open EPR/RO-DEMO-01/2026/0900 and issue the recovery certificate.
3. **`ro-recovery` → Recovery certificates**: serve the demand notice; attach two lathes (record why it cannot wait);
   sell them above the reserve. **`ro-apfc`** issues an 8F notice to the bank. **`ro-recovery`** records the rest paid —
   the certificate closes, and the PMVBRY exclusion lifts once the ledger shows the dues paid.
4. Also: **`ro-oic`** grants instalments (at most 72); an arrest needs a notice to show cause first.
5. **`ho-compliance` / `ho-recovery` → Proceedings and recovery**: the two reports.

## Disaster recovery, training, camps, totalisation, the foreign agency, the composite death claim
*Tests: `tests/e2e/test_small_rest.py`*

1. **`ndc-adc` → DR site**: replication lag per database against the RPO (simulated); run a database failover drill
   (one-time code) — the steps and the RTO against the target.
2. **`pdnasa-trainer` → Training sandbox**: a course for three trainees practising as member A and the DA.
3. **`ro-nan` → NAN camp**: an inoperative-account request for MOHAN DEMO — the reference and what happens next.
4. **`ho-iwu` → Agreements › Totalisation claims**: route a claim with periods abroad and in India.
5. A foreign agency (machine login `foreign-agency-demo`) verifies a certificate of coverage: status and posting
   only, the worker's name masked.
6. **`claimant-a` → Death claim › Composite claim (PF and EDLI)**: both claims under one reference.

## Vigilance
*Tests: `tests/e2e/test_vigilance.py`, `services/workflow-service/tests/test_vigilance.py`*

1. **`caiu-investigator` → Risk signals**: a signal reviewed as *confirmed* has *Refer to vigilance*; fill the subject,
   the office and the allegation. A benign signal has no button (and the API refuses it). The referral gets a VCN.
2. **`vigilance-investigator` (Chief Vigilance Officer) → Vigilance cases**: open the case — the complainant is shown —
   and *Assign inquiry* (one-time code). The inquiry goes to the zone of the office, due in 90 days.
3. **`zo-vigilance` → Vigilance cases**: only the zone's cases; the complainant reads *Masked — known to the CVO only*;
   report the findings (partly substantiated, the report, a recommendation, the evidence examined).
4. **CVO**: decide — e.g. *Minor penalty proceedings*, or *Return for further inquiry*. The history lists each step.
5. Any other role (e.g. `ro-oic`) gets 403 on the vigilance API; every read is in the audit log (`vigilance.case.read`).
6. **`hrm-employee` → HRM › Sensitive posts**: `ro-cashier` is overdue for rotation (posted June 2023). *Vigilance
   clearance* for an officer named in an open case is *withheld* (HR is not told why); once the CVO closes the case, a
   new request is *cleared*. Posting an officer to the cash section needs a current clearance for that purpose.
7. **CVO → Vigilance cases**: the rotation list and every clearance, with the case that withheld it.

## The member's home page and the phone layout
*Tests: `tests/e2e/test_member_home.py`, `apps/web/src/features/member/memberHome.test.ts`, `apps/web/src/features/MemberHome.test.tsx`*

1. **`member-b`** signs in and lands on *Your PF at a glance*: the total across member IDs, service, the pension
   estimate; *To do* shows "Complete your KYC (PAN)" and, without a nomination, "Add your nominee".
2. **`member-g`** (changed jobs) sees both member IDs with their balances and statuses.
3. *What do you want to do?* — pick "I changed jobs" and follow *Transfer my PF* into the existing transfer form.
4. Narrow the browser to phone width (or use the device toolbar at 360px): the menu becomes one *Menu* button,
   the page is a single column and nothing scrolls sideways.

## International workers are members
*Tests: `tests/e2e/test_international_worker_member.py`, `services/claim-service/tests/test_international_workers.py`*

1. **`worker-expat`** signs in as a member (UAN 100000000907, United States): the full member menu, passbook and
   profile, which says *International worker: Yes* with a note on the rules. *View › International worker coverage*
   shows the employment and that there is no agreement with their country.
2. **Claims**: every advance is shown not available, "Not available to international workers …"; final settlement
   waits for the age of 58 (or a nationality with an agreement in `international_workers.final_settlement_on`).
3. **`emp-preparer` → ECR**: a row above the wage ceiling for this member is a warning (`W-IW-FULL-WAGES`), not an
   error; for anyone else it is still `E-EPS-CEILING`.
4. **Form 11**: the employer declaring a joinee an international worker (country of origin required) makes them one
   everywhere; declaring otherwise clears it. `member-a` has no coverage page.

## Member services: e-Nomination, attestation, bank switch, auto-transfer, exits
*Tests: `tests/e2e/test_member_mobility.py`, `services/{member,claim,workflow}-service/tests/test_*mobility*.py`,
`services/member-service/tests/test_nominations.py`*

1. **`member-a` → e-Nomination**: add the spouse (60%) and a minor son (40%, with a guardian); sign with the mock
   Aadhaar e-sign. A non-family nominee is refused while "I have a family" is ticked. **`member-f`** is refused:
   her Aadhaar is not verified. *Know your UAN*: name, date of birth, the mobile's last four digits and any
   six-digit code (mock) find the UAN.
2. **`member-f` → Claim**: an advance for ₹5,000 goes to *Pending employer attestation*, not to the office.
   **`emp-signatory` → Claim attestations**: attest it (it is then approved automatically) or reject it with a reason.
3. **`member-a` → Claims**: on a claim still with the office, *Switch bank account* offers her two KYC-verified
   accounts (…0001 and …4321).
4. **`member-g` → Service › Auto-transfer**: AL-0905 (exited, ₹80,000) can move into the primary member ID AL-0906.
   Confirm with the one-time code; the ledger posts it without a Form 13, an employer or an officer.
5. **`emp-preparer` → Exit bulk upload**: lines `uan,account_link_id,date_of_exit,reason`; each valid line becomes an
   exit waiting for the signatory, the rest are reported. *Exit correction* corrects a marked date; **`emp-signatory`
   → Member › Approvals** approves both kinds. *Employer-initiated JD*: the signatory files a Joint Declaration
   with the member's consent (mock OTP); it goes straight to the DA.

## Compliance: defaulters, demands and VISHWAS
*Tests: `tests/e2e/test_compliance.py`, `services/compliance-service/tests/test_compliance.py`,
`services/reporting-service/tests/test_compliance_reads.py`*

1. **`ro-da-compliance` → Establishments & compliance › Defaulters, cases and VISHWAS**: establishments with a month
   unpaid past its due date or an open demand. *Open a compliance case* on one; `ro-apfc` sees it in the cases list.
2. **`member-a` → Public lookups**: *Defaulting establishments* — name, office and months in default.
3. **`emp-owner` → Dashboards › Compliance summary**: each wage month filed, paid, paid late or unpaid, with its demands.
4. **`emp-signatory` → Payments › VISHWAS**: apply to settle the open 14B damages; the page says 30% will be payable
   (illustrative). **`ro-apfc`** approves it (step-up bound to the revised amount): the old demands are waived and
   one revised demand raised.
5. **`emp-signatory` → Payments › Demands (14B / 7Q)**: *Pay now* on the revised demand; after the bank callback it
   shows **PAID**.

## Policy changes that move money — interest, TDS and pensions
*Tests: `tests/e2e/test_policy_money.py`, `services/contribution-service/tests/test_interest.py`,
`services/claim-service/tests/test_tds.py`, `services/pension-service/tests/test_pensions.py`*

The rule set has three more sections, changed the same way (drafted by `ho-policy`, published by `ho-analyst`
with a one-time code). *Effect, with worked examples* shows each change before it is approved.

1. **Interest.** Under *Interest on PF accounts* the rate for each financial year (8.25% for 2025-26).
   **`ho-finance` → Interest crediting** shows, per account, the interest due on the twelve month-end balances,
   what is already credited and what is to be credited; *Credit interest* (one-time code, bound to the total)
   posts one balanced journal per account dated 31 March. Now revise the 2025-26 rate (say 8.50%) and publish:
   the same screen shows only the difference, *Post the revision* credits it, and `member-b`'s passbook shows
   "Interest for 2025-26 revised to 8.5%: difference". A year that has not ended, or has no declared rate, is
   refused.
2. **TDS.** Under *Tax deducted at source* the taxed claim types, the threshold, the rates with and without a
   verified PAN, the service after which no tax is deducted, and whether Form 15G / 15H waives it. The tax is
   worked out when **`ro-cashier`** instructs the payment, under the rules in force that day, then fixed:
   **`member-c`** (left employment after about 3½ years, PAN verified) claims a ₹60,000 final settlement, it is
   settled automatically, and the claim shows *Claim amount ₹60,000 · TDS ₹6,000 · Paid to your bank ₹54,000*.
   Change the rate with a PAN to 5% and publish: the next payment deducts ₹3,000. A Form 15G / 15H filed on
   *My claims* waives it for the year.
3. **Pensions.** Under *Pension formula* the divisor, salary cap, weightage, early-pension reduction and minimum
   pension, and whether a change also revises **pensions in payment** (never downwards), optionally with effect
   from an earlier date. Raise the minimum pension with effect from two months ago and publish:
   **`ro-pension` → Pension revisions** lists each pension it raises with the arrears for the months already
   paid; approve with a one-time code. **`pensioner-a` → My pension** shows the new amount, how it is worked out,
   the rule set, and the arrears credit. Members see their own estimate on *Profile & notices*.

If a version is already scheduled for a later date, today's change must first be carried into it (a same-day
correction of that version); otherwise it would undo the change from its date, and publishing is refused.

## Explore: stakeholders, lifecycles, manuals
From the home page (no login): **Stakeholders** — the hierarchy from the Central Board to the district office, and
everyone outside EPFO; choose *Enforcement Officer* for his login and what he does. **Lifecycles** — choose *F06
Compliance*: the chain from a CAIU signal through the inspection, the file, the inquiry and the order to recovery,
planned steps dashed in red; choose a step for who does it and what follows. **User manuals** — the manuals the UI
tests produced, by role (after `python3 scripts/publish_manuals.py`).

## The Code's transition: ₹25,000 from 17 September 2026, VISHWAS, 2026, instalments

1. As `ho-policy`, open Policy administration: `demo-rules-2026.2` is in force from 17 Sep 2026 (EPS and EDLI ceilings
   ₹25,000); the baseline is superseded.
2. As `emp-preparer`, file September 2026 with a member on ₹20,000: EPS wages up to ₹17,333 are accepted (16 days at
   ₹15,000, 14 at ₹20,000); ₹20,000 is refused with the expected figure. In October ₹20,000 is right; a row with no EPS
   wages gets a warning that the member belongs to the pension scheme.
3. As `emp-signatory`, Returns › VISHWAS: each open 14B demand shows its recalculation (arrears x rate x months), or why it
   is not eligible (a default after 14 June 2024, 7Q interest unpaid). Apply with the undertaking not to appeal; as
   `ro-apfc`, approve — one revised demand replaces them.
4. EEC, 2026: as `emp-preparer`, register an employee who joined in January 2024 (Members › Register). As
   `emp-signatory`, Returns › *EEC, 2026*: choose them, enter ₹14,000 a month, *Work out the dues* — 27 months, the
   employee's share waived, ₹100 damages — then declare (step-up) and pay the challan; the employee's ledger shows the
   period credited.
5. As `ro-oic`, on a recovery certificate, *Refer beyond your power* with 48 instalments: it goes to Head Office. As
   `ho-analyst` (CPFC), *Instalment referrals*: grant with a guarantee of six instalments, or refuse with reasons.
6. As `ro-oic`, grant instalments on a recovery certificate: a bank guarantee of one instalment is required; 40
   instalments are refused (Head Office only). As `ro-recovery`, record a missed instalment: recovery resumes.

## Data held, not asked (P2.21a)

1. `member-g` (GIRISH DEMO) changed jobs: when his new employer's first return is paid, his old member ID's balance moves
   to the new one by itself, and he gets a message — no Form 13, no confirmation.
2. A member who left more than two months ago sees, on the home page, *Ready for you: Final settlement — ₹…*: the claim
   form opens with the member ID and the full amount filled in; review and confirm.
3. A member of 58 who has left with ten years' service is offered the monthly pension (Form 10D) the same way.

## A death EPFO learns from the civil registry (P2.21b)

1. Run `python3 scripts/crs_death_feed.py`: the civil registry (mock) reports that VIJAY DEMO (UAN 100000000916) died
   yesterday. The answer: matched by Aadhaar, his member ID closed as death in service. Run it again with the same
   `--registration-no`: the same answer, nothing done twice.
2. Log in as `claimant-b` (MEENA DEMO, his wife and nominee): *What you can claim* shows the PF (Form 20) and EDLI
   (Form 5IF) amounts with their workings. *File PF and EDLI together*, confirm with the one-time code: a composite claim.
   Below, Form 10D has his UAN filled in: file the family pension.
3. As `ro-pro`, Office › *Deaths from the civil registry*: VIJAY's record, and any that matched nobody (try
   `python3 scripts/crs_death_feed.py --name "NOBODY DEMO" --dob 1950-01-01 --no-aadhaar`).
4. As `member-a`, View › UAN card › *In your DigiLocker*: *Send my e-UAN card to DigiLocker* — a few seconds later it is
   issued with a document URI.
5. As `zo-audit`, the daily audit extract: *Claims settled automatically* and how many are in the post-audit sample; the
   sampled ones are flagged `AUTO_SETTLEMENT_SAMPLE`, ready for an alert to the office.

## Erroneous EPS contributions rectified (P2.19c, HO circular WSU/2025/E-961539)

1. As `emp-preparer`, register a joinee with date of joining 4 Jan 2016 and file a return for a month of 2016 with wages
   of ₹40,000 and EPS on ₹15,000; `emp-signatory` approves, submits and pays.
2. As `do-caseworker`, Office › Ledger › *EPS rectification*: the joinee's member ID, *I — EPS allowed to a member not
   eligible*, that month, a notesheet and the reason (joined after 1 Sep 2014 above the ceiling). The working shows the
   EPS remitted and the interest.
3. As `ro-apfc`, approve it (one-time code): A/c 10 → A/c 1. The next return with pension wages for the joinee is
   refused with `E-EPS-NOT-ELIGIBLE` and corrected — the employer's whole 12% to EPF.
4. Scenario II is the same in reverse; for an exempted establishment, the trust remits the EPS due and `ro-cashier` records
   it under *EPS rectification*.

## Every rejection says what fixes it (P2.23b)

1. As `member-a`, file an illness advance of ₹1,50,000 (it goes to DA → AO). As `do-caseworker`, open the case:
   *Recommend to Reject*, choose *A document the claim needs is missing* — the form shows what the member will read —
   and confirm. As `ro-ao`, reject it.
2. As `member-a`, open the claim: the reason, the officer's note, and *What to do* with *Go there* to the claim form.
3. Claims page: a type not open to the member says why and what to do — e.g. a final settlement while in service links to
   *Mark Exit*; one too soon after leaving gives the date it opens.

## Retirement view (P2.23a)

1. As `member-a`, View › *Retirement view*: the PF balance today, the wages, and at 58 the PF, its monthly income, the
   pension and the total — as a share of the wages then.
2. Enter 10 in *Voluntary PF (VPF)* and *Show with VPF*: a second row — what VPF costs a month now, the larger PF at 58,
   and, when the member's own contributions pass ₹2,50,000 a year, the note that the interest on the part above is taxable.

## Edge cases (P2.19a)

1. An ECR row with pension wages for a re-employed pensioner (UAN `100000000901`, PPO-DEMO-0001) is refused with
   `E-EPS-PENSIONER`; *Apply the corrections* moves the employer's whole 12% to EPF.
2. An ECR row for a month after a member's exit is refused with `E-AFTER-EXIT`: correct the exit date (court-ordered back
   wages), then file a supplementary return.
3. When the employer marks a member's exit as death in service, the member's own claims not yet paid close with the reason
   (the nominees claim through Form 20), and an approved claim's debit comes back to the account.

## Disablement pension (EPS para 15)

1. Log in as `member-disabled` (SURESH DEMO): Pension (Form 10D). *Apply for monthly pension* is refused — 7 years of
   service. Open *Apply for a disablement pension*: date 12 Aug 2026, a Medical Board or RPwD certificate, tick
   *permanently and totally unfit*, apply: ₹1,500 a month from 21 Aug 2026, no reduction at 46.
2. As `do-caseworker` (DA Accounts), Office › Pension claims: the claim is marked *Disablement pension (para 15)*, with the
   certificate to scrutinise; it goes through the same desks to the PPO.

## A trust's past accumulations reconciled (PAST ACCUM VDR RECO)

1. After the surrender (above), `ro-exemption` has credited the trust's members (Past accumulation ingestion).
2. As `ro-cashier`, record the trust's demand draft (Office › Ledger › VDR) for the amount.
3. As `do-caseworker` (DA Accounts), Office › Ledger › *Past accumulations — receipts reconciliation*: credited,
   received, outstanding; tick the demand draft, add an SDS or securities receipt with HO's reference if any, enter the
   Form SE-6 total, propose.
4. As `ro-apfc`, approve (step-up): *Reconciled*, nothing outstanding — or *still short* with the amount to come.

## Finding your way: side or top menu, Find a screen

1. Log in as `ro-apfc`. The menu is down the side: the group holding the page is open, the item marked. Type
   *recovery* in *Filter the menu*; only matching items stay. Tick *Show items not built* to see the menus EPFO has
   that the POC does not build.
2. Press Ctrl+K (or *Find a screen*), type *legal*, press Enter: the legal cases open.
3. Choose *Top menu* in the header: the familiar bar returns, and the choice stays for this browser. Log in as
   `member-a`: the top bar is the default for members.
4. As `pensioner-a`, press *A+* three times: the text grows to 150% on every page and stays so after a reload; *A*
   returns to the default.

## What the tests cover

```bash
make test         # unit tests of every service, the gateway and the shared packages
make e2e          # Journeys A–E on the running stack
make security     # the 25 must-deny tests of docs/permissions.md
make resilience   # broker down, consumer down, gateway restart (stops and starts containers)
```

Results of the last full run: `docs/test-report.md`.
