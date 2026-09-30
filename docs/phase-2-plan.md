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
| **P2.5b** | Death and EDLI claims, beneficiary shares, physical intake at the PRO counter, identity validation (family pension deferred to P2.6) | **Done** (29 Sep 2026) |
| **P2.5c** | Ledger locks, document attestation views, establishment freeze / de-freeze, office Annexure K files and reconciliation | **Done** (29 Sep 2026) |
| **P2.5d** | Claim scrutiny as the CITES manuals set it: the Claim Approval Docket at every level, recommend to approve / reject with the account status, rejection only at the final level (an intermediate "Recommend to Reject" returns to the initiator), Start-Stop Claim, one-time code on every officer action | **Done** (30 Sep 2026) |
| **P2.6a** | Establishment record and changes: KYC through mock registries, bank accounts, exemption, branches (Form 2A), Form 5A, contractors of a principal employer; profile and configuration changes as requests the office decides; OLRE scrutiny (DA Compliance, e-file) and the APFC's coverage decision | **Done** (30 Sep 2026) |
| **P2.6b** | Signatory request / revoke letters, DSC and e-sign registration with the office's approval (Authorized eSign List), the signatory's pending approvals; family pension (Form 10D by a widow / widower or child) | **Done** (30 Sep 2026) |
| **P2.7a** | Returns and payments: arrear and supplementary returns, cancelling an unpaid TRRN, the office rejecting a return before posting or a payment stuck at the bank, the returns dashboard, 14B / 7Q demands on late payment, direct challans (administrative charges; miscellaneous 14B / 7Q) and their knock-off (DA Compliance → SS) | **Done** (30 Sep 2026) |
| **P2.7b** | Office ledger work: receipts outside the challan flow (VDR) allocated to TRRNs or rejected, reversal of a posted journal, recredit of a rejected transfer-in, Appendix E with the CITES manual's four types (DA proposes, APFC approves) | **Done** (30 Sep 2026) |
| **P2.7c** | Member-facing ledger: annual statement, taxable interest split, Form 10C cash withdrawal (pension withdrawal benefit by Table D, paid from EPS) | **Done** (30 Sep 2026) |
| **P2.7d** | Primary member ID: the latest member ID with contributions, over the member's Aadhaar-verified set; claims only against it, whole-balance claims (final settlement, Form 10C, death claims) only when the rest of the set is transferred; Form 13 only into it (checked when filed and when approved) | **Done** (30 Sep 2026) |
| P2.8 | The rest: principal-employer tags (contractor), exempted establishments' past accumulations, compliance and VISHWAS, international workers, grievance extras, public lookups, audit, NDC, HRM, DO dashboards | |

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

## P2.5b — how it is built

- Synthetic data: GANESH DEMO (UAN 100000000901, AL-0901) died in service on 15 Jul 2026; nominations LAKSHMI
  DEMO (spouse, 60 %, persona `claimant-a`) and ARJUN DEMO (son, 40 %). New persona `ro-pro-counter` (fo.pro_intake).
- claim-service (`app/api/death_routes.py`): a nominee files Form 20 (PF: the member ID's balance) or Form 5IF
  (EDLI: `edli_benefit` under the rules in force — wages × multiplier, plus a share of the average balance
  capped, between the assured minimum and maximum; synthetic average wages ₹15,000). The claim goes straight to
  review through the normal officer chain; beneficiaries come from the nomination (or a list given with the claim,
  or are added later with no share). The APFC amends a share with a reason (one-time code); payment is refused
  until the shares add up to 100 %; at settlement each beneficiary's paid amount is recorded, net of any share
  settled in the legacy system. The PRO counter inwards paper forms; pension updations go to the pension office.
- `ClaimDecisionRecorded.v1` now carries `fund`: an EDLI claim is debited to AC21_EDLI, not the member's account.
  New event `PhysicalClaimInwarded.v1` (pension-service turns a pension updation into a NEW, PHYSICAL activity);
  `BeneficiaryShareAmended.v1` moved to phase 1.
- member-service: identity validation at the counter matches name and date of birth with the record and keeps the
  KYC status at that moment (audited). An exit marked `DEATH_IN_SERVICE` records the date of death in claim-service.
- Deferred: family pension (Form 10D by a widow / child, P2.6), the composite claim (CCF), a dedicated EDLI
  decision step, and paying each beneficiary to their own bank account (one payment per claim for now).

## P2.5c — how it is built

- workflow-service (`app/api/locks_routes.py`): a claim case, and a Form 13 case (`ledger_lock:` in its YAML), lock
  the member's ledger while open; the lock goes with the case when it finishes. A lock whose owner is gone or has
  expired is orphaned and refuses officers' decisions on that member (`/problems/ledger-locked`) until the OIC
  releases it with a reason and a one-time code (`LockReleased.v1`, now phase 1). Seed: a dead annual-accounts batch
  left one on ESHA DEMO (UAN 100000000005).
- Engine: `produces_document` keeps a signed document on the case (the employer's DSC on Form 13, mock) and
  `requires_viewed` refuses the step until the officer has opened it (`attestation-views`, audited).
- `config/processes/establishment-freeze.yaml`: the zone / OIC / HO freezes an establishment; de-freeze is
  maker-checker (APFC recommends, OIC orders). employer-service now consumes `ProcessTransitioned.v1` and shows the
  freeze to the employer; contribution-service refuses ECR approval and submission while it stands.
- ANNEXURE K FILE / RECO (claim-service, a projection of `TransferPosted.v1`: inward, outward, within the office),
  reconciled against the UAN, the amount and the previous member ID being emptied; ANNEXURE K VDR RECO
  (contribution-service) against the VDR receipt amount. Both with one-time codes.
- Not built: the annual-accounts batch and ECR posting do not take locks yet (only the seeded orphan shows those
  scopes); Annexure K for exempted establishments (`/office/exempted/annexure-k/...`) stays planned.

## P2.5d — how it is built

Source: the CITES user manuals (`../manuals`, reviewed in `docs/reviews/cites-manuals-vs-poc.md`).

- **Claim Approval Docket.** The CAD was an accounts-wing document made after approval; in CITES it is the Claim
  Approval Docket the initiator generates and every verifier and the approver generates again before acting.
  `POST /office/claims/{claimId}/cad` is now open to the scrutinising officers while the claim is under review and
  keeps one version per level; `CADGenerated.v1` carries the officer's role, and the work queue refuses a
  recommendation or decision without a docket of that role made since the last decision (`/problems/docket-required`).
  Payment uses the last docket's figures. The accounts wing views the dockets.
- **Recommendation.** The initiator recommends to approve or to reject and records the account status (Operative /
  Inoperative / Dormant), confirmed with a one-time code like every other officer action.
- **Rejection routing.** Only the final level of the amount's chain rejects. An intermediate level forwards the
  recommendation, or — disagreeing with an approval — recommends rejection, which returns the claim to the
  initiator's worklist; the initiator re-forwards it as "Recommend to Reject". The final level sees Approve / Send
  back after a recommended approval and Reject / Send back after a recommended rejection.
  `CaseDecisionSubmitted.v1` carries the recommendation, and the member's timeline says which was recommended.
- **Start-Stop Claim.** The initiator stops a claim under scrutiny with a reason (it leaves every queue and shows
  under Stopped claims) and restarts it later.
- Kept: a verifier approving within its financial limit is our amount-band chain (the last role for the amount is
  final). Not built from the review: the beneficiary login and uploads, the EDLI three-tab calculation screen and
  officer e-sign of the summary sheet, full data entry at the PRO counter, Form 10C cash, Appendix E.

## P2.6a — how it is built

- employer-service (`app/api/establishment_routes.py`): KYC of the establishment (PAN, GSTIN, TAN, CIN, LIN)
  through a mock registry (a number containing `00000` is "not found"); remittance bank accounts and exemption
  (seeded); branches with sub-codes `<registration no>/001…`, shown in the configuration; Form 5A kept by version,
  signed with a one-time code standing in for DSC / e-sign; a principal employer's contractors with the work order.
- Changes are not edits: `PATCH /employers/me` (address, contact) and configuration changes (establishment type,
  industry) open a change request; the APFC of the establishment's office approves (the record changes) or
  rejects it. One open request of each kind at a time.
- OLRE: a registration verified by the mock registry waits for the DA (Compliance), who views the documents and
  records scrutiny, opening the compliance e-file; then the APFC decides coverage (date and type).
- employer-service now has office postings (seeded) for jurisdiction. New persona `ro-da-compliance`.
- The web pages *Establishment* (employer) and *OLRE and establishment changes* (office) were drafted by codex from
  a written spec and reviewed.

## P2.6b — how it is built

- employer-service (`app/api/signature_routes.py`): the owner registers a signatory's DSC (serial, issuer, validity;
  an expired certificate is refused) or Aadhaar e-sign (mock), with a one-time code; uploads the signed request
  letter (PDF, SHA-256 kept); the APFC approves or rejects it. After a signatory is revoked, the signed revoke letter
  goes to the office; approving it ends the signatory's registration. The *Authorized eSign List* shows all of it.
  Registration is not yet required before a signatory approves (returns, KYC, attestations) — noted for later.
- workflow-service: `GET /employers/me/pending-approvals` lists the engine steps waiting for the establishment's
  signatory (Form 13 attestation, Joint Declarations, operator-marked exits) with the operation to perform.
- pension-service (`app/api/family_routes.py`): the spouse or a child on record (the member's nomination) files
  Form 10D on the member's death; it runs through the same desks as a member's Form 10D, and the worksheet uses
  the family-pension formula in the rules (`pension.family`: 50% of the member's formula pension for the spouse,
  a quarter of that for a child, with minimums; no minimum service). The PPO is issued in the claimant's name.
- Web: the Authorized eSign List on *Establishment*, pending approvals on *Member actions*, the office's DSC /
  e-sign decisions on *OLRE* (drafted by codex, reviewed), and the family-pension section on the claimant page.

## P2.7a — how it is built

- contribution-service: `type=ARREAR | SUPPLEMENTARY` returns need the month's regular return posted; a
  supplementary return may only carry members missing from the posted returns, an arrear return only members in
  them (`E-SUPP-ALREADY-FILED`, `E-ARREAR-NOT-FILED`); warnings about the whole workforce do not apply to them.
- An unpaid TRRN is cancelled by the signatory (one-time code bound to the amount) and the wage month is free
  again; the DA (Accounts) rejects a submitted return before it is paid; Cash rejects a payment stuck at the bank
  (the mock bank's new `STUCK` scenario never answers) and the challan can be paid again.
  `ChallanStatusChanged.v1` tells the mock bank; `ChallanGenerated.v1` makes a direct challan payable.
- Late payment: posting a return paid after the due date (`late_payment.due_day` of the next month) raises a 14B
  damages demand (yearly rate by months of delay) and a 7Q interest demand (yearly rate by days) — new rule section
  `late_payment`, validated and publishable. The employer pays them with a miscellaneous direct challan (posted to
  `DAMAGES_14B` / `INTEREST_7Q`); the DA (Compliance) knocks the demands off against it and the SS approves.
  Administrative charges go by a direct challan too (`AC02_ADMIN`).
- The returns dashboard shows each wage month: the regular return, arrear and supplementary returns, due date,
  paid late or not.

## P2.7b — how it is built

- contribution-service (`app/api/ledger_routes.py`). **Receipts (VDR)**: Cash records a cheque / DD / unmatched
  credit with a one-time code; the DA (Accounts) allocates it to an unpaid TRRN of the same establishment — the
  challan is paid and the return posted by the same code path as an online payment (late-payment demands included)
  and `ChallanStatusChanged.v1` (`SETTLED_OFFLINE`) stops the mock bank from taking an online payment for it — or
  rejects it (a dishonoured cheque). What a VDR entry covers in EPFO is not fully confirmed; this is the reading used.
- **Reversal**: a posted contribution, direct challan or Appendix E journal is reversed by a new reversing
  journal (never edited); a member ID is never taken below zero. **Recredit**: a transfer-in the receiving office
  rejected goes back to the member ID it came from. `LedgerReversed.v1` now carries what was reversed; claim-service
  applies any reversal to balances, workflow and member-service clear "transferred" on a recredit.
- **Appendix E** (CITES manual): *Other* (employee, employer and EPS up or down, balanced by an office adjustment
  account), *interest on returns* (employee and employer only), *1.16% to EPS* (from the employer share, never more
  than it holds), *excess interest debit*; each with the notesheet number, date, remarks and optional PDF. The DA
  proposes, the APFC approves (balances are checked again), then it is posted (`LedgerAdjusted.v1`) and shown in the
  passbook.
- Moved to P2.8: principal-employer tags and exempted past accumulations (their actors have no persona yet).

## P2.7c — how it is built

- **Form 10C cash**: a new claim type `PENSION_WITHDRAWAL` in the rules (form 10C) — two months after leaving,
  under 9½ years of service, once per member ID, never settled automatically. The limit is new rule kind
  `max_from: eps_table_d`: the illustrative Table D factor for the completed years of service × wages at the EPS
  ceiling (`table_d_factor_x100`, validated; the policy editor offers it). It runs through the officer chain with the
  Claim Approval Docket, and `ClaimDecisionRecorded.v1` `fund: EPS` debits the EPS pool (`AC10_EPS`), not the member's
  PF. On a running stack the type reaches members only when a rule set containing it is published (the e2e test
  publishes it through the HO maker-checker flow if needed) — adding a claim type needs no code.
- **Annual statement** (`/members/me/annual-statements/{fy}`): per member ID, the opening balance (with the balance
  brought forward), the year's contributions, withdrawals, transfers, interest and adjustments, and the closing
  balance, employee and employer shares. Interest counts in the year it is earned for.
- **Taxable interest**: interest on the employee's own contributions above `tds.taxable_interest_threshold_paise`
  (illustrative ₹2,50,000 a year) is taxable, at the year's rate on the excess; the rest is not. Shown with the
  working, marked illustrative.
- Not built from the CITES review: "send back to DA for wage corrections" on Form 10C, NCP-day deductions.

## P2.7d — how it is built

Source: the Samadhan Setu tracker (7 of its 35 issue types are about the primary member ID: "Requested member id does
not match with the primary member id", "all services are not transferred to primary member id", "Unable to inward
form 5IF due to incorrect Primary Member ID marked", "Transfer-in Member ID must be primary MemberID") and the office
screens (*Primary UAN*, *Primary Member ID*, "(P)", "Part of AADHAAR verified set").

- Rule (`epfo_persistence.member_ids.primary_member_id`): among the member IDs not transferred out, the latest-joined
  one that has received a contribution; if none has, the latest-joined. It is worked out over the member's
  **Aadhaar-verified set**: every UAN with the same verified Aadhaar (member-service keeps a reference, never the
  number). Seed: BHARAT DEMO's older UAN 100000000903 (AL-0903, ₹50,000 not transferred) is in his set.
- member-service recomputes it when a contribution is posted (a new member ID becomes primary with its first
  contribution), a member ID is registered, a transfer is posted or recredited, and publishes
  `PrimaryMemberIdChanged.v1`; the service history, the member 360 view and the UAN set show it.
- claim-service: a claim on a secondary member ID is refused ("Requested member ID does not match with the primary
  member ID (AL-…)"); a final settlement or Form 10C, and a Form 20 / 5IF death claim, also need every other member ID
  of the set emptied ("All services are not transferred to the primary member ID: AL-… holds ₹…").
- workflow: Form 13's "to" member ID must be primary when filed, and again when the AO approves (the primary may
  have moved; rejecting stays possible).
- Web: "P" against the primary member ID in the service history and the claim screen; the transfer form offers only
  the primary as the target.
