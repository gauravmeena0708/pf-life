# Phase 2 — plan and progress

Phase 2 is every operation marked **P, phase 2** in `docs/endpoint-catalogue.md` (177 at the start). It is built
in slices, each finishing journeys the POC already demonstrates; a slice is done when its operations are **W**,
its menus in the web app are clickable, and unit, end-to-end and must-deny tests pass on the running stack.

| Slice | Scope | Status |
|---|---|---|
| **P2.1** | Dates of exit (member Mark Exit; employer marks, signatory approves), service history, the member's pending / processed applications, Form 13 transfer (member → present employer → DA → AO; ledger moves the balance), Annexure K | **Done** (28 Sep 2026) |
| **P2.2** | Employer member registration (single, bulk; new UAN or a new member ID under an existing one), Form 11, member KYC (PAN, bank) through mock verifiers and the signatory's approval, KYC bulk with error list, missing details, active-member export, the employee's contribution ledger, UAN card, account readiness | **Done** (28 Sep 2026) |
| **P2.3** | Pension office and pensioner self-service: pension enquiry (8 tabs), updation activities (DA initiates, APFC settles) and tracker, overdue life certificates, suspend / resume (held months released), mock Jeevan Pramaan DLC and signed callback, PPO, slips, bank change, declarations, public pension enquiries behind the demo CAPTCHA | **Done** (29 Sep 2026) |
| **P2.4** | Pension settlement: Form 10D desk by desk (DA Accounts IDS → AO → DA Pension worksheet → APFC Pension → PPO → initial arrear DA → SS → APFC e-sign → dispatch), scheme certificate and its surrender, service aggregation, transfers-in, CPPS monthly run with the mock sponsor bank's paid statement and reconciliation, BRS | **Done** (29 Sep 2026) |
| **P2.5a** | Claim lifecycle and office tools: eligibility preview for one form, documents, withdrawal before a decision, member and office audit trails, the CAD (accounts wing), payment scrolls with return reconciliation, forms filed with a claim, member 360 view (purpose recorded), inoperative accounts | **Done** (29 Sep 2026) |
| P2.5b | Death and EDLI claims, beneficiary shares, physical intake at the PRO counter, identity validation, family pension | Next |
| P2.5c | Ledger locks, document attestation views, establishment freeze / de-freeze, office Annexure K files and reconciliation | |
| P2.6 | Establishment registration and configuration, Form 5A, branches, DSC / e-sign approvals | |
| P2.7 | Returns, receipts and ledger: arrear / supplementary ECR, demands, direct challans, 14B/7Q knock-offs, VDR rejection, reversals, recredits | |
| P2.8 | The rest: compliance and VISHWAS, international workers, grievance extras, public lookups, audit, NDC, HRM, DO dashboards | |

Operations marked **?** (scope unconfirmed, e.g. *ECR Approval*, *VDR Member Beneficiary*) wait until their
meaning is confirmed.

## P2.1 — how it is built

- **Processes on the engine** (`config/processes/employer-exit.yaml`, `transfer-form13.yaml`). The engine gained
  generic `account` and `date` form rules, checked against a projection of member accounts in workflow-service
  (whose account, at which establishment, exited, already transferred), and `reads` operations (a member's own case).
  `ProcessTransitioned.v1` now says whether the case ended (`terminal`) and whether the member sees it.
- **Owners**: member-service records exits (`MemberExitMarked.v1`) and keeps the member's applications;
  contribution-service posts the transfer journal (`TransferPosted.v1`) and serves Annexure K; claim-service keeps
  its balances and exit dates from those events.
- **Data**: a UAN can now have several member IDs (contribution-service keys members by member ID). Synthetic
  member D has two: AL-0008 (previous, exit not marked) and AL-0009 (current).

## P2.2 — how it is built

- member-service registers joinees (`MemberRegistered.v1` → contribution, claim, workflow) and runs KYC requests:
  a labelled mock verifier (UIDAI / NSDL / penny-drop) answers first, then the employer's signatory approves with
  step-up (DSC / e-sign). An approved KYC changes the member record and publishes `MemberKycUpdated.v1`
  (claim-service updates the PAN flag that sets the TDS rate).
- Deferred from this slice: UAN activation and self-allotment (a login per new member), exit corrections and
  exit-bulk (exits already need the signatory's approval per member), member location mapping (branches, P2.6),
  employer-initiated Joint Declaration.
- Found: interest for a year in which a member ID's balance was later transferred was credited to the emptied
  member ID. It is now credited to the member ID the money went to, and "already credited" is read from the
  interest postings themselves.

## P2.3 — how it is built

- pension-service owns it all. A pension is credited monthly only while IN_PAYMENT; a lapsed life certificate lets
  the APFC (Pension) suspend it; a new certificate (Jeevan Pramaan, or a physical one recorded as an updation
  activity) resumes it and the held months are credited on that day.
- Updation activities are a small maker-checker inside pension-service (not the engine): the DA (Pension) — new
  persona `ro-da-pension` — initiates, the APFC settles, rejects or sends back; only a settled activity changes the
  pension. A pensioner's bank change is such an activity.
- The gateway now asks the demo CAPTCHA for the four public pension enquiries as well as the TRRN lookup.
- Not modelled: beneficiaries / family pension, commutation, recovery and TDS on pension (the enquiry shows them
  empty), the pension-disbursing bank's own enquiry.

## P2.4 — how it is built

- pension-service holds the Form 10D claim as a small state machine; each step is its own endpoint and role, and
  the officer who took a step cannot check it (the APFC (Pension) both approves the worksheet and e-signs the PPO,
  as in the Pension Manual, with other officers in between). The worksheet uses the pension formula in the rule
  set in force on the date the pension starts; the e-signature is bound (step-up) to the initial arrear amount.
- Dispatching the PPO puts the pension in payment and credits the months since it started (the initial arrear).
- CPPS: a run lists the month's credits; the sponsor bank's paid statement arrives by a signed callback, or — when
  CPPS reconciles before one arrived — the mock bank answers at once (accounts ending 0000 are returned). The
  office's BRS compares its scroll with the bank's debits.
- New personas: `member-e` (retired member), `ro-ss-pension` (SS Pension), `ndc-cpps` (CPPS operator).
- Not built: family pension (Form 10D by claimants), Special 10D, higher-pension options, the legacy bank-wise
  disbursement lists.

## P2.5a — how it is built

- claim-service: a member may withdraw a claim only before an approving officer decides (the work-queue case
  closes); documents are checked (type, magic bytes, 1 MB) and kept with their SHA-256 — a stand-in for the object
  store. The CAD (new persona `ro-fa-accounts`, F&A accounts wing) fixes gross, interest included, TDS and net,
  with the rule and static-data versions; a payment made after it uses its figures. A payment scroll pays every
  approved claim of the office whose debit is posted; its reconciliation lists paid, pending and returned claims.
- member-service: the member 360 view needs a purpose, is limited to the officer's office (a zonal officer sees
  the zone) and is written to the audit log. contribution-service: inoperative accounts (no credit for 36 months).
- Found: the gateway asks for step-up on every POST of an operation marked for it, so a "preview" flag on the
  scroll POST could never work; the preview is its own read-only endpoint (`GET /office/payment-scrolls/ready`).
