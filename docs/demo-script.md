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

## What the tests cover

```bash
make test         # unit tests of every service, the gateway and the shared packages
make e2e          # Journeys A–E on the running stack
make security     # the 25 must-deny tests of docs/permissions.md
make resilience   # broker down, consumer down, gateway restart (stops and starts containers)
```

Results of the last full run: `docs/test-report.md`.
