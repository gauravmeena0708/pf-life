# Endpoint Catalogue — EPFO Functional Coverage

> **Companion to `init.md` §3.** `init.md` §3.1 lists the *minimum working* endpoints. This catalogue lists **every EPFO function the platform is expected to cover eventually**, with a delivery status for each, so no function is left out or has an invented success response.
>
> All forms, payment types and processes are named for **functional coverage only**. Nothing here asserts current statutory rates, ceilings, eligibility conditions or SLAs; those live in `config/demo-rules.yaml` marked `ILLUSTRATIVE_ONLY` (see §0.5 of `init.md`).

## Legend

| Status | Meaning | Implementation expectation |
|---|---|---|
| **W** | Working POC | Implemented and tested end to end. Only used for rows that a Journey A–E step needs, or that `init.md` §2.3 lists as working coverage for an interface |
| **M** | Mock integration | Implemented against a deterministic mock adapter for an external system (bank, Aadhaar, Jeevan Pramaan, MCA, GSTN, etc.) |
| **P** | Planned contract | OpenAPI contract in `contracts/planned/` with schema, access policy, owner and milestone. Endpoint returns `501` Problem Details with `type: /problems/planned`, **never** a fake success |
| **?** | Definition pending | Function is known to exist but its exact semantics must be confirmed by an EPFO domain owner before the contract is written. Placeholder row only; nothing is built |

Phase: **1** = this POC, **2** = next stage, **3** = later. Every **W** row is phase 1. A row moves P → M → W only with its tests.

Owner `platform` = shared operations tooling at NDC (event replay, Issue Tracker, DR, sandboxes), not a business service.

Markers: 💰 money-changing or filing command — requires `Idempotency-Key`, an expected state/version (`If-Match`), and emits an auditable event. 🔐 sensitive — requires a step-up / transaction-intent confirmation (`init.md` §6.3); for office actions this means maker-checker with a named second approver.

Rules that apply to every row:
- **One owner per route.** When other services are involved, the owner emits an event; it never writes their data.
- **Each row is one operation.** Reads and state transitions are separate rows because their access policies differ.
- **Every inbound callback** (`/integrations/**`) verifies a signature, a provider event ID, a timestamp within a replay window, and deduplicates durably.
- **Public lookups** that take an identifier (PPO, TRRN, UAN) are `POST` with CAPTCHA/OTP proof and return minimal fields, so identifiers never appear in enumerable URLs or logs.

---

## 1. Public information and establishment search

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /public/schemes` | Scheme catalogue (EPF, EPS, EDLI) — illustrative text | W | 1 | reporting |
| `GET /public/offices` | Office locator by state/district/pincode | W | 1 | workflow |
| `GET /public/statistics` | Aggregate statistics, small-group suppression | W | 1 | reporting |
| `POST /public/demo-calculations/epf` | Illustrative EPF contribution calculator | W | 1 | contribution |
| `POST /public/demo-calculations/pension` | Illustrative pension estimate calculator | W | 1 | pension |
| `GET /public/establishments?query=&mode=&match=&office_id=&city=&district=&establishment_type=&exemption_status=&status=&page=` | **Establishment search** by code, registration, pincode, name or industry; filter by location, type, exemption and coverage | W | 1 | employer |
| `GET /public/establishments/{estId}` | Public profile: name, registration, office, location, type, industry, coverage, verification and exemption | W | 1 | employer |
| `GET /public/demo-challenges` | One-use arithmetic proof for synthetic public lookup demo | M | 1 | gateway |
| `GET /public/establishments/{estId}/e-report-card` | Establishment **e-Report Card**: wage-month filing/payment history, counts and totals only | W | 1 | reporting |
| `POST /public/trrn-status-lookups` | **TRRN / challan status** lookup with wage month, issue/payment times and next step; one-use synthetic demo proof (production CAPTCHA pending) | M | 1 | contribution |
| `GET /public/defaulting-establishments` | Published defaulter list (synthetic) | W | 1 | compliance |
| `GET /public/circulars` | Circulars / notifications catalogue (synthetic, versioned documents) | W | 1 | intelligence |
| `POST /public/pension/life-certificate-lookups` | **Jeevan Pramaan / life-certificate status** by PPO number or Jeevan Pramaan transaction ID (CAPTCHA, minimal disclosure) | M | 1 | pension |
| `POST /public/pension/ppo-lookups` | **Know your PPO** (by bank account + DoB / member ID) | W | 1 | pension |
| `POST /public/pension/payment-enquiries` | Pension payment enquiry (month-wise credited / not credited) | W | 1 | pension |
| `POST /public/pension/status-enquiries` | Pension application / PPO status enquiry | W | 1 | pension |
| `POST /public/claims/status-lookups` | Claim status by reference (OTP proof; no PII in response) | W | 1 | claim |
| `POST /public/inoperative-accounts/searches` | Inoperative-account helpdesk search (step-up before any balance is shown) | P | 3 | contribution |
| `POST /public/grievances` | Grievance intake from a non-logged-in person (OTP-verified contact) | W | 1 | grievance |
| `POST /public/grievances/status-lookups` | Grievance status by registration number (OTP proof) | W | 1 | grievance |

## 2. Establishment registration and configuration

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /employers/registration-requests` | New establishment registration request | W | 1 | employer |
| `POST /employers/registration-requests/{reqId}/verification-evidence` | Submit demo verification evidence (PAN/CIN/GSTIN/LIN) to mock registry adapter (Journey A1) | M | 1 | employer |
| `GET /employers/registration-requests/{reqId}` | Registration status | W | 1 | employer |
| `GET /employers/me` | Establishment profile (active establishment chosen via `X-Establishment-Id`, validated server-side) | W | 1 | employer |
| `GET /employers/me/configuration` | **Establishment configuration** (read-only, seeded): coverage date, exemption status, coverage type, jurisdiction office, sub-codes, applicable schemes | W | 1 | employer |
| `POST /employers/me/configuration/change-requests` 🔐 | Request configuration change (office-approved) | W | 1 | employer |
| `GET /employers/me/change-requests` | The establishment's change requests and the office's decisions | W | 1 | employer |
| `PATCH /employers/me` 🔐 | Update address / contact — creates a change request, not a direct edit | W | 1 | employer |
| `GET /employers/me/ownership-declaration` | **Form 5A** ownership / management declaration — view | W | 1 | employer |
| `PUT /employers/me/ownership-declaration` 🔐 | Form 5A — submit / amend | W | 1 | employer |
| `POST /employers/voluntary-coverage-requests` | Voluntary coverage request | P | 3 | employer |
| `GET /employers/me/kyc` | Establishment KYC status: PAN, TAN, GSTIN, CIN, LIN | W | 1 | employer |
| `POST /employers/me/kyc/{kycType}` 🔐 | Seed / update establishment KYC (mock registry verification) | M | 1 | employer |
| `GET /employers/me/branches` | Sub-codes / branches / departments | W | 1 | employer |
| `POST /employers/me/branches` | Create sub-code | W | 1 | employer |
| `GET /employers/me/bank-accounts` | Establishment bank accounts used for remittance | W | 1 | employer |
| `GET /employers/me/exemption` | Exemption details (PF trust, relaxation) | W | 1 | employer |
| `POST /employers/me/closure-requests` 🔐 | Closure / business-discontinued declaration | P | 3 | employer |
| `POST /employers/me/office-transfer-requests` 🔐 | Transfer establishment to another office jurisdiction | P | 3 | employer |
| `GET /employers/me/contractors` | Principal employer: linked contractors | W | 1 | employer |
| `POST /employers/me/contractors` | Principal employer: register / link contractor | W | 1 | employer |
| `GET /employers/me/contractors/{contractorId}/compliance` | Principal employer: contractor remittance compliance | P | 2 | reporting |
| `POST /employers/me/ecr-filings/{filingId}/principal-employer-tags` | Contractor: tag ECR members to a principal employer | P | 2 | contribution |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /office/establishment-registrations` | **OLRE**: new registrations of the office awaiting scrutiny / coverage | W | 1 | employer |
| `GET /office/establishment-registrations/{reqId}/documents` | DA (Compliance) views documents of a new registration (FO-interface >> OLRE >> View Documents) | W | 1 | employer |
| `POST /office/establishment-registrations/{reqId}/scrutiny-notes` | DA (Compliance) records scrutiny and opens the compliance e-file | W | 1 | employer |
| `POST /office/establishment-registrations/{reqId}/coverage-decisions` 🔐 | Circle officer's coverage decision on a new establishment | W | 1 | employer |
| `GET /office/establishment-change-requests` | Establishment change requests of the office, by state | W | 1 | employer |
| `POST /office/establishments/{estId}/change-requests/{requestId}/decisions` 🔐 | Decide configuration change / closure / office-transfer requests | W | 1 | employer |
| `POST /integrations/mca/registrations` | MCA SPICe+ / AGILE-PRO auto-registration feed (signed) | M | 2 | employer |
| `POST /integrations/shram-suvidha/registrations` | Shram Suvidha common-registration feed (signed) | M | 3 | employer |
| `GET /partners/liquidators/claims/{claimId}` | Liquidator / resolution professional views EPFO dues claim | P | 3 | compliance |
| `GET /employers/me/dashboard` | Employer home alerts and Dashboards (pending KYC, member-detail approvals, missing details) | W | 1 | reporting |

## 3. Employer operators, signatories, DSC and e-sign

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /employers/me/operators` | List operators | W | 1 | employer |
| `POST /employers/me/operators/invitations` 🔐 | Invite operator with scoped permissions (a privileged grant) | W | 1 | employer |
| `POST /employers/me/operators/{operatorId}/revocations` 🔐 | Revoke operator (Journey A9) | W | 1 | employer |
| `GET /employers/me/signatories` | List authorised signatories | W | 1 | employer |
| `POST /employers/me/signatories/authorisations` 🔐 | Authorise signatory | W | 1 | employer |
| `POST /employers/me/signatories/{signatoryId}/revocations` 🔐 | Revoke / replace signatory (Journey D5) | W | 1 | employer |
| `POST /employers/me/signatories/{signatoryId}/request-letters` | Upload the scanned, signed **signatory registration request letter**; *Authorized eSign List* shows its status (Establishment > e-sign Registration) | W | 1 | employer |
| `POST /employers/me/signatories/{signatoryId}/revoke-letters` | Upload the signed **signatory revoke letter** that backs a revocation, with its own status (*Authorized eSign List*: Signatory Revoke Request) | W | 1 | employer |
| `POST /employers/me/signatories/{signatoryId}/dsc-registrations` 🔐 | Register DSC for signatory | M | 1 | employer |
| `POST /employers/me/signatories/{signatoryId}/esign-registrations` 🔐 | Register Aadhaar e-sign for signatory | M | 1 | employer |
| `GET /employers/me/signature-registrations` | **Authorized eSign List**: each signatory's DSC / e-sign registration and revoke requests with their status | W | 1 | employer |
| `GET /office/signature-registrations` | DSC / e-sign registrations and revoke letters of the office awaiting approval | W | 1 | employer |
| `POST /office/establishments/{estId}/signature-registrations/{regId}/decisions` 🔐 | Field office approval of DSC / e-sign registration | W | 1 | employer |
| `GET /employers/me/pending-approvals` | Items awaiting DSC/e-sign (KYC, transfers, claims, JD) | W | 1 | workflow |

## 4. Employer-side member management

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /employers/me/members?status=` | Employees of this establishment (own establishment only; feeds the ECR wizard in Journey A3) | W | 1 | member |
| `POST /employers/me/members` | Register new joinee / generate UAN (mock Aadhaar) | W | 1 | member |
| `POST /employers/me/members/bulk-registrations` | Bulk registration file | W | 1 | member |
| `POST /employers/me/members/{uan}/declarations` | **Form 11** new-joinee declaration | W | 1 | member |
| `GET /employers/me/members/{uan}/contribution-ledger` | Wage and contribution ledger for own employee | W | 1 | contribution |
| `POST /employers/me/members/{uan}/exits` 🔐 | Mark exit with date and reason | W | 1 | member |
| `POST /employers/me/members/{uan}/exit-corrections` 🔐 | Date-of-exit correction | W | 1 | member |
| `GET /employers/me/kyc-approvals` | Member KYC requests awaiting employer approval | W | 1 | member |
| `POST /employers/me/kyc-approvals/{requestId}/decisions` 🔐 | Approve / reject member KYC (bank, PAN, Aadhaar seeding) | W | 1 | member |
| `GET /employers/me/joint-declarations` | Joint Declarations awaiting attestation (tier-2 process `joint_declaration`) | W | 1 | member |
| `POST /employers/me/joint-declarations/{jdId}/decisions` 🔐 | Attest / reject Joint Declaration (tier-2 process `joint_declaration`) | W | 1 | member |
| `POST /employers/me/joint-declarations` 🔐 | Employer-initiated Joint Declaration | W | 1 | member |
| `GET /employers/me/transfer-requests` | Form 13 transfer requests awaiting attestation | W | 1 | claim |
| `POST /employers/me/transfer-requests/{transferId}/decisions` 🔐 | Attest / reject transfer | W | 1 | claim |
| `GET /employers/me/claim-attestations` | Claims awaiting employer attestation | W | 1 | claim |
| `POST /employers/me/claim-attestations/{claimId}/decisions` 🔐 | Attest / reject claim | W | 1 | claim |
| `GET /employers/me/higher-pension-options` | Member joint options for higher pension awaiting validation | W | 1 | pension |
| `POST /employers/me/higher-pension-options/{optionId}/validations` 🔐 | Validate option and upload wage details | W | 1 | pension |
| `POST /employers/me/higher-pension-options/{optionId}/dues-previews` | Dues the uploaded wages give, before the signatory confirms | W | 1 | pension |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /employers/me/approvals` | Member > Approvals queue (exits and other member changes awaiting the signatory) | W | 1 | member |
| `POST /employers/me/approvals/{approvalId}/decisions` 🔐 | Approve / reject a queued member change | W | 1 | member |
| `POST /employers/me/kyc-bulk-uploads` | Member > KYC BULK upload | W | 1 | member |
| `GET /employers/me/kyc-bulk-uploads/{uploadId}/errors` | Bulk KYC error list | W | 1 | member |
| `POST /employers/me/members/exit-bulk-uploads` 🔐 | Member > Exit-Bulk upload | W | 1 | member |
| `PATCH /employers/me/members/{uan}/profile` 🔐 | Fill missing member details (only details the record lacks; a recorded detail changes through a Joint Declaration) | W | 1 | member |
| `POST /employers/me/members/{uan}/location-mappings` | Member Location Mapping to branches | W | 1 | member |
| `GET /employers/me/members/active-export` | Download active members with UAN and KYC (Dashboards > Active Members) | W | 1 | member |

## 5. Returns, challans and payments

ECR **types** (regular / arrear / supplementary) are a field on one ECR resource. **Demands** (14B damages, 7Q interest, standalone admin charges, higher-pension dues) are assessed elsewhere and arrive as payable items; they are not ECR types. **How** money is paid (net banking, bank counter) is a **payment channel** on the payment intent, not a remittance type.

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /employers/me/ecr-filings` 💰 (`type=REGULAR`) | Create **regular** monthly ECR (upload / wizard) | W | 1 | contribution |
| `POST /employers/me/ecr-filings` 💰 (`type=ARREAR`) | **Arrear ECR** (wage-revision arrears) | W | 1 | contribution |
| `POST /employers/me/ecr-filings` 💰 (`type=SUPPLEMENTARY`) | **Supplementary / revised ECR** for missed members | W | 1 | contribution |
| `POST /employers/me/ecr-filings/{filingId}/validations` | Schema + business validation | W | 1 | contribution |
| `POST /employers/me/ecr-filings/{filingId}/approvals` 🔐 | Signatory approval | W | 1 | contribution |
| `POST /employers/me/ecr-filings/{filingId}/submissions` 💰🔐 | Submit → generate TRRN | W | 1 | contribution |
| `POST /employers/me/ecr-filings/{filingId}/cancellations` 💰🔐 | Cancel an **unpaid** TRRN and release the wage-month lock | W | 1 | contribution |
| `GET /employers/me/ecr-filings/{filingId}` | Filing detail and status | W | 1 | contribution |
| `GET /employers/me/ecr-filings?wageMonth=&type=` | Return filing history | W | 1 | contribution |
| `GET /employers/me/challans` | Challan list | W | 1 | contribution |
| `GET /employers/me/challans/{trrn}` | Challan detail by TRRN | W | 1 | contribution |
| `GET /employers/me/challans/{trrn}/receipt` | Payment receipt / CRN | W | 1 | contribution |
| `POST /employers/me/challans/{trrn}/payment-intents` 💰🔐 (`channel=NET_BANKING`) | Pay challan via mock bank | M | 1 | payment-simulator |
| `POST /employers/me/challans/{trrn}/payment-intents` 💰🔐 (`channel=BANK_COUNTER`) | **Cash / bank-counter payment** channel — whether it is still permitted, and for what, is unconfirmed | ? | 3 | payment-simulator |
| `GET /employers/me/demands` | Payable demands: 14B damages, 7Q interest, admin charges, higher-pension dues (created from compliance / pension events) | W | 1 | contribution |
| `POST /employers/me/demands/{demandId}/payment-intents` 💰🔐 | Pay a demand (**14B / 7Q / admin charges**) | W | 1 | payment-simulator |
| `GET /employers/me/compliance-summary` | Month-wise filing / payment compliance for this establishment | W | 1 | reporting |
| `POST /integrations/mock-bank/payment-confirmations` 💰 | Signed bank confirmation callback | M | 1 | payment-simulator |
| `POST /integrations/mock-bank/payment-returns` 💰 | Signed bank return / failure callback | M | 1 | payment-simulator |
| `POST /partners/sandbox/payroll/ecr-filings` 💰 | B2B payroll API ECR upload | M | 1 | contribution |

**Office-side receipts, adjustments and reversals.** These are field-office processes, never employer-facing payment types. Every row is maker-checker, and every ledger effect goes through `contribution-service` as a new journal with a reversal link.

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /office/receipts/unreconciled` | Unreconciled / suspense receipts | W | 1 | contribution |
| `POST /office/receipts/{receiptId}/trrn-adjustments` 💰🔐 | **TRRN adjustment**: allocate an excess / unallocated amount against a future TRRN | W | 1 | contribution |
| `POST /office/vdr-entries` 💰🔐 | **VDR entry** — record a receipt that arrived outside the online ECR/TRRN flow (e.g. cheque/DD, transfer-in, Annexure K, LIC). EPFO material reportedly expands VDR as *Valuable Document Register* (unconfirmed); the exact categories are unconfirmed | W | 1 | contribution |
| `POST /office/vdr-entries/{vdrId}/ecr-reconciliations` 🔐 | Reconcile a VDR entry with the corresponding ECR, and flag late payment for 14B / 7Q | ? | 3 | contribution |
| `POST /office/vdr-entries/{vdrId}/special-credits` 💰🔐 | **VDR Special** — exceptional direct credit to a member account, with evidence and competent-authority approval. EPFO treats it as a high-risk process; semantics unconfirmed | ? | 3 | contribution |
| `POST /office/ledger-adjustments` 💰🔐 (`type=APPENDIX_E`) | **Appendix E** — field-office adjustment of a member's opening balances (taxable / non-taxable / total), also used for PF→EPS diversion. Not an employer remittance | W | 1 | contribution |
| `GET /office/ledger-adjustments` | Appendix E adjustments proposed, approved and rejected | W | 1 | contribution |
| `POST /office/ledger-adjustments/{adjustmentId}/approvals` 🔐 | Second approval of a ledger adjustment | W | 1 | contribution |
| `GET /office/ecr-filings` | Returns submitted but not yet paid (to reject, or to reject a stuck payment) | W | 1 | contribution |
| `POST /office/ecr-filings/{filingId}/rejections` 🔐 | Reject an ECR **before** posting | W | 1 | contribution |
| `GET /office/ecr-filings?state=PENDING_OFFICE_APPROVAL` | **ECR Approval** queue (top menu on the APFC login; exact scope not yet confirmed — see §16) | ? | 3 | contribution |
| `POST /office/ecr-filings/{filingId}/approvals` 🔐 | Office approval of an ECR held for approval (*ECR Approval* menu; scope to be confirmed) | ? | 3 | contribution |
| `POST /office/vdr-entries/{vdrId}/rejections` 🔐 | **VDR Rejection** — reject a VDR entry with a reason (top menu *VDR Rejection*) | W | 1 | contribution |
| `POST /office/vdr-entries/{vdrId}/member-beneficiaries` 🔐 | **VDR Member Beneficiary** — attach the member / beneficiary to whom a VDR receipt is credited (top menu; exact meaning to be confirmed) | ? | 3 | contribution |
| `POST /office/ledger-journals/{journalId}/reversals` 💰🔐 | Reverse an **already posted** journal (new reversing entries; never edit in place) → `LedgerReversed.v1` | W | 1 | contribution |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /employers/me/returns/dashboard` | Return monthly dashboard by wage month | W | 1 | contribution |
| `POST /employers/me/direct-challans` 💰🔐 | **Direct Challan**: administrative / inspection charges challan, or miscellaneous challan for 14B damages and 7Q interest (Payments > ECR/Return filing > Direct Challan > Challan Entry) | W | 1 | contribution |
| `POST /office/establishments/{estId}/damages-knock-offs` 💰🔐 | Knock off auto-calculated 14B / 7Q against a miscellaneous challan (FO INTERFACE >> 14B/7Q Knock Off) | W | 1 | contribution |
| `GET /office/damages-knock-offs` | Knock-offs, open demands and paid miscellaneous challans with a balance | W | 1 | contribution |
| `POST /office/damages-knock-offs/{knockOffId}/approvals` 🔐 | SS approves the knock-off | W | 1 | contribution |
| `POST /office/vdr-entries/{vdrId}/eo-certifications` 🔐 | Enforcement Officer certifies a revised ECR in the VDR-ECR correction process | ? | 3 | contribution |
| `PUT /ho/config/interest-rates/{financialYear}` 🔐 | Record the approved annual interest rate (CBT recommendation, Ministry concurrence). In the POC the rate is a field of the rule set (`interest.rates_bp`), published through policy administration | W | 1 | contribution |


**Added from the Samadhan Setu integration spec** (`../samadhan-setu files/PF_LIFE_INTEGRATION_SPECIFICATION.md`, checked against the tracker issues)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /office/ecr-filings/{filingId}/payment-rejections` 🔐 | Cash / Accounts rejects an unpaid or erroneous challan stuck in pending bank status (tracker: "Unable to reject ecr payment") | W | 1 | contribution |
| `POST /office/transfers/{transferId}/recredits` 💰🔐 | Recredit a rejected transfer-in back to the member ledger (VDR recredit; tracker: "Recredit of transfer-in rejected cases") | W | 1 | contribution |

## 6. Member self-service

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /members/uan-activations` | UAN activation (mock OTP / mock face authentication) | M | 2 | member |
| `POST /members/uan-allotments` | Self UAN allotment via mock Aadhaar face auth (UMANG-style) | M | 2 | member |
| `POST /members/uan-lookups` | **Know your UAN** (OTP-verified) | W | 1 | member |
| `GET /members/me` | Profile | W | 1 | member |
| `GET /members/me/identity-assurance` | Assurance level | W | 1 | member |
| `PATCH /members/me/contact-details` 🔐 | Change mobile / email (Journey D1) | W | 1 | member |
| `GET /members/me/kyc` | KYC status (Aadhaar, PAN, bank) | W | 1 | member |
| `POST /members/me/kyc/bank-accounts` 🔐 | Seed / change bank account (mock penny-drop, employer approval) | W | 1 | member |
| `POST /members/me/kyc/{kycType}` 🔐 | Seed PAN / other KYC (mock) | W | 1 | member |
| `POST /members/me/joint-declarations` 🔐 | Profile correction request (Joint Declaration) (tier-2 process `joint_declaration`) | W | 1 | member |
| `GET /members/me/employment-history` | Service history across linked employments | W | 1 | member |
| `POST /members/me/exits` 🔐 | Member-marked exit (when employer has not marked it); refused while another process for the member ID is ongoing | W | 1 | member |
| `GET /members/me/applications?status=` | *Recent Pending Applications* / *Recent Processed Applications* (Service History page); also the "process already ongoing" list that blocks a new Mark Exit | W | 1 | member |
| `GET /members/me/passbook` | Passbook across all accounts linked to the caller (no member ID parameter) | W | 1 | contribution |
| `GET /members/me/accounts/{accountLinkId}/passbook` | Passbook for one linked account; `accountLinkId` is an opaque ID validated against the caller | W | 1 | contribution |
| `GET /members/me/annual-statements/{financialYear}` | Annual account slip | W | 1 | contribution |
| `GET /members/me/tax/taxable-interest?financialYear=` | Taxable vs non-taxable interest split | W | 1 | contribution |
| `GET /members/me/tax/form-16a?financialYear=` | TDS certificate (Form 16A) | P | 3 | claim |
| `POST /members/me/tax/form-15g-15h` | Upload Form 15G / 15H | W | 1 | claim |
| `GET /members/me/nominations` | e-Nomination (Form 2) — view | W | 1 | member |
| `POST /members/me/nominations` 🔐 | e-Nomination — submit with mock e-sign | W | 1 | member |
| `GET /members/me/sessions` | Session history | W | 1 | gateway |
| `POST /members/me/security-reports` | Report suspicious activity | W | 1 | member |
| `POST /members/me/account-recovery-requests` 🔐 | Controlled, reviewed account recovery (Journey D5) | W | 1 | member |
| `GET /security/account-recovery-requests` | Review queue of account-recovery requests (Journey D5) | W | 1 | member |
| `POST /security/account-recovery-requests/{requestId}/decisions` 🔐 | Approve or reject an account-recovery request; approval restores the verified contact details (Journey D5) | W | 1 | member |
| `GET /members/me/notifications` | Notifications (projection fed by claim / payment / grievance events — see §14) | W | 1 | member |
| `GET /members/me/uan-card` | UAN card | W | 1 | member |
| `GET /members/me/transfers/auto` | Auto-transfer status on job change | W | 1 | claim |
| `POST /members/me/transfers/auto/{transferId}/confirmations` 🔐 | Confirm auto-transfer | W | 1 | claim |
| `GET /members/me/transfers/{transferId}/annexure-k` | **Annexure K** transfer statement | W | 1 | contribution |
| `GET /members/me/pension-scheme-certificate` | Scheme certificate status | W | 1 | pension |
| `POST /members/me/higher-pension-options` 🔐 | Submit joint option for higher pension | W | 1 | pension |
| `GET /members/me/higher-pension-options/{optionId}` | Higher-pension application status | W | 1 | pension |
| `GET /members/me/higher-pension-options` | The member's higher-pension options and the eligibility date (illustrative) | W | 1 | pension |


**Designed from the Samadhan Setu analysis** (not in the spec files; see `docs/samadhan-setu-mapping.md`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /members/me/account-status` | **Pre-flight:** readiness of each linked member account before filing — KYC, UAN–member-ID link, exit date, freeze, active ledger locks, unmigrated legacy transactions — as explicit blocker codes | W | 1 | member |
| `GET /members/me/service-history` | **Pre-flight:** service per member ID — contributory months, NCP days, pension-service months, transfer status — for pension and final-settlement decisions | W | 1 | member |

## 7. Member claims, transfers and pension applications

`claim-service` owns PF withdrawals, settlements and transfers; `pension-service` owns pension applications and the scheme certificate. Eligibility comes from the illustrative rule engine, never hard-coded.

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /members/me/claims/eligible-types` | Available claim types with rule version and reasons (Journey B3) | W | 1 | claim |
| `POST /members/me/claims` 💰 (`formType=FORM_31`) | **Advance / partial withdrawal** (purpose as sub-type) | W | 1 | claim |
| `POST /members/me/claims` 💰 (`formType=FORM_19`) | **Final PF settlement** | W | 1 | claim |
| `POST /members/me/claims` 💰 (`formType=FORM_10C`) | **Pension withdrawal benefit** (cash benefit) | W | 1 | claim |
| `POST /members/me/pension-scheme-certificates` 🔐 | **Scheme certificate** request (Form 10C option) | W | 1 | pension |
| `POST /members/me/pension-applications` 💰 (`formType=FORM_10D`) | **Monthly pension** application | W | 1 | pension |
| `GET /members/me/pension-applications` | The member's pension application: its desk-by-desk progress, the PPO number once issued | W | 1 | pension |
| `POST /members/me/transfers` 💰🔐 (`formType=FORM_13`) | **Transfer** of PF between member IDs / exempted trusts | W | 1 | claim |
| `GET /members/me/transfers/{transferId}` | Transfer status | W | 1 | claim |
| `GET /members/me/claims` | List own claims | W | 1 | claim |
| `GET /members/me/claims/{claimId}` | Claim detail + timeline (Journey B7) | W | 1 | claim |
| `POST /members/me/claims/{claimId}/confirmations` 🔐 | Transaction-intent confirmation (Journey B3) | W | 1 | claim |
| `POST /members/me/claims/{claimId}/cancellations` 🔐 | **Cancel** an unsettled claim (renamed from `…/withdrawals`; allowed only before a checker decision — see `ClaimStateMachine` in `claim-service.yaml`) | W | 1 | claim |
| `POST /members/me/claims/{claimId}/documents` | Upload supporting document (PDF / JPEG / PNG up to 1 MB, content checked, SHA-256 kept; stored by claim-service in the POC in place of the object store) | W | 1 | claim |

**Death and EDLI (claimant ≠ member)**

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /claimants/death-claims` 💰 🔐 (`formType=FORM_20`) | PF death claim by nominee / legal heir | W | 1 | claim |
| `POST /claimants/death-claims` 💰 🔐 (`formType=FORM_5IF`) | **EDLI** insurance claim | W | 1 | claim |
| `POST /claimants/death-claims` 💰 (`formType=CCF_DEATH`) | Composite claim covering several death benefits | P | 3 | claim |
| `GET /claimants/death-claims/{claimId}` | Status (claimant verified separately; no member PII beyond entitlement) | W | 1 | claim |
| `POST /claimants/family-pension-applications` 💰 🔐 (`formType=FORM_10D`) | Widow / child / orphan pension | W | 1 | pension |
| `GET /claimants/family-pension-applications` | Status of the family pension application, desk by desk | W | 1 | pension |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /office/transfers` | Form 13 transfers awaiting the DA's verification or the AO's decision | W | 1 | claim |
| `POST /office/transfers/{transferId}/verifications` | DA verifies service at both establishments before the AO decides | W | 1 | claim |
| `POST /office/transfers/{transferId}/decisions` 🔐 | Process a Form 13 transfer between member IDs / offices | W | 1 | claim |
| `POST /office/edli-claims/{claimId}/decisions` 💰🔐 | Decide EDLI assurance-benefit claim | W | 1 | claim |
| `GET /office/edli-claims` | EDLI claims admitted by the office, waiting for the EDLI section | W | 1 | claim |
| `POST /office/edli-claims/{claimId}/benefit-previews` | The EDLI benefit from the verified average wages, before deciding | W | 1 | claim |


**Added from the Samadhan Setu integration spec** (`../samadhan-setu files/PF_LIFE_INTEGRATION_SPECIFICATION.md`, checked against the tracker issues)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /claimants/death-claims/{claimId}/beneficiaries` 💰 | Inward an additional co-beneficiary / legal heir on an open death claim | W | 1 | claim |
| `POST /members/me/claims/{claimId}/re-disbursement-requests` 💰 | Member submits corrected bank details after a payment return, without re-filing the claim | W | 1 | claim |


**Designed from the Samadhan Setu analysis** (not in the spec files; see `docs/samadhan-setu-mapping.md`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /members/me/claims/eligibility-preview?formType=` | **Pre-flight:** evaluate one form type before filing — eligible or not, blockers from account status, maximum amount, required documents, rule version | W | 1 | claim |
| `GET /members/me/claims/{claimId}/audit-trail` | **Post-submission:** member's view of every state change on own claim (time, state, role, reason; officer names withheld) | W | 1 | claim |
| `PUT /members/me/claims/{claimId}/bank-details` 🔐 | **Post-submission:** switch a claim not yet in payment to another **KYC-verified** bank account of the member (after a return, use `…/re-disbursement-requests`) | W | 1 | claim |
| `GET /members/me/claims/{claimId}/bank-details` | The member's KYC-verified bank accounts a claim can be switched to, and whether it still can be | W | 1 | claim |

## 8. Office claim processing and member accounts

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /office/work-queue` | Jurisdiction-filtered task queue | W | 1 | workflow |
| `GET /office/cases/{caseId}` | Case detail | W | 1 | workflow |
| `POST /office/cases/{caseId}/assignments` | Assign | W | 1 | workflow |
| `POST /office/cases/{caseId}/recommendations` 🔐 | Initiator's "Recommend to Approve / to Reject" with the account status (Operative / Inoperative / Dormant) | W | 1 | workflow |
| `POST /office/cases/{caseId}/stops` | **Stop Claim Processing** with a reason (initiator; a parallel activity must finish first) | W | 1 | workflow |
| `POST /office/cases/{caseId}/restarts` | **Restart Claim** from the stopped-claims list | W | 1 | workflow |
| `GET /office/stopped-cases` | Stopped claims of the office | W | 1 | workflow |
| `POST /office/cases/{caseId}/decisions` 🔐 | Decision → `CaseDecisionSubmitted.v1`; only the final level rejects, an intermediate "Recommend to Reject" returns the claim to the initiator | W | 1 | workflow |
| `POST /office/cases/{caseId}/second-approvals` 🔐 | Dual control for high-value / high-risk cases | W | 1 | workflow |
| `POST /office/claims/{claimId}/payment-instructions` 💰🔐 | Settlement payment instruction → `PaymentInstructed.v1` (Journey B6) | W | 1 | claim |
| `POST /office/claims/{claimId}/reissues` 💰🔐 | Re-issue after bank return (Journey B6) | W | 1 | claim |
| `GET /office/payment-scrolls/ready` | Approved claims of the office ready for the next payment scroll (ledger debit posted, account not frozen), with the total | W | 1 | claim |
| `POST /office/payment-scrolls` 💰🔐 | Batch approved settlements into a payment scroll → `PaymentScrollGenerated.v1` | W | 1 | claim |
| `POST /office/payment-scrolls/{scrollId}/return-reconciliations` 💰🔐 | Reconcile a bank return scroll, open re-settlement cases | W | 1 | claim |
| `POST /office/physical-claims` | **Physical claim intake**: register a paper claim, scan, data entry | W | 1 | claim |
| `POST /office/physical-claims/{intakeId}/identity-validations` | UAN allocation / Aadhaar validation before settlement (mock) | W | 1 | member |
| `GET /office/members/{uan}` | Member 360 view (jurisdiction + purpose checked, audited) | W | 1 | member |
| `POST /office/members/{uan}/freezes` 🔐 | **UAN / member-ID freeze** with reason and evidence (tier-2 process `member_freeze`) | W | 1 | member |
| `POST /office/members/{uan}/defreezes` 🔐 | De-freeze, maker-checker (tier-2 process `member_freeze`) | W | 1 | member |
| `POST /office/accounts/interest-postings` 💰🔐 | Annual interest crediting run (illustrative rate) | W | 1 | contribution |
| `GET /office/accounts/interest-postings?financialYear=` | Interest run preview: the rate in the rule set in force, interest due per account (monthly running balance), already credited, the difference to credit, and earlier runs | W | 1 | contribution |
| `GET /office/accounts/inoperative` | **Inoperative account** identification | W | 1 | contribution |
| `POST /office/accounts/{accountLinkId}/reactivations` 🔐 | Inoperative account reactivation | P | 3 | contribution |
| `POST /office/tds/computations` | TDS on withdrawal (illustrative rules) | P | 3 | claim |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /office/member-change-requests` | Joint Declaration / profile-change queue (initiator view) (tier-2 process `joint_declaration`) | W | 1 | member |
| `POST /office/member-change-requests/{requestId}/recommendations` | JD initiator (DA) recommends (tier-2 process `joint_declaration`) | W | 1 | member |
| `POST /office/member-change-requests/{requestId}/verifications` | JD verifier (SS or AO) verifies (tier-2 process `joint_declaration`) | W | 1 | member |
| `POST /office/member-change-requests/{requestId}/decisions` 🔐 | JD approver decides (competent authority by change type) (tier-2 process `joint_declaration`) | W | 1 | member |
| `GET /office/member-change-requests/pendency` | RPFC-I monitors JD pendency (tier-2 process `joint_declaration`) | W | 1 | member |
| `POST /office/freeze-cases/{caseId}/verifications` | Freeze-case verification step (DA → SS/AO → APFC/RPFC-II → OIC; tier-2 process `member_freeze`) | W | 1 | workflow |
| `POST /office/establishments/{estId}/freezes` 🔐 | Freeze an establishment | W | 1 | employer |
| `POST /office/establishments/{estId}/defreezes` 🔐 | De-freeze an establishment, maker-checker | W | 1 | employer |
| `POST /office/accounts/{accountLinkId}/crowdsource-verifications` | Inoperative-account crowdsourcing verification through co-workers' logins | P | 3 | member |
| `POST /office/outreach-camps/{campId}/assisted-requests` | Requests taken at Nidhi Aapke Nikat camps | P | 3 | workflow |


**Added from the Samadhan Setu integration spec** (`../samadhan-setu files/PF_LIFE_INTEGRATION_SPECIFICATION.md`, checked against the tracker issues)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /office/claims/{claimId}/cad` 💰 | Generate the **Claim Approval Docket (CAD)** at this level (CITES: the initiator, each verifier and the approver regenerate it before acting): interest split, TDS and net payable, with the rule and static-data versions used | W | 1 | claim |
| `GET /office/claims/{claimId}/cad` | View the latest Claim Approval Docket and every level's version | W | 1 | claim |
| `GET /office/system/cad-static-data` | Diagnostic view of CAD static reference data (interest tables, bank branch master) and its version (tracker: "Failed to load CAD static Data") | W | 1 | claim |
| `PUT /office/death-claims/{claimId}/beneficiaries/{beneficiaryId}/shares` 🔐 | Amend a beneficiary's share (nominee deceased, court order, share already settled in legacy, guardian appointment) | W | 1 | claim |
| `GET /office/death-claims/{claimId}/shares-summary` | Allocated vs legacy-settled vs disbursed vs pending share of a death claim | W | 1 | claim |
| `POST /office/claims/{claimId}/re-disbursement-approvals` 💰🔐 | APFC authorises a new payment after a return, without reopening adjudication | W | 1 | claim |
| `GET /office/members/{uan}/locks` | Active locks on a member ledger (annual accounts, claim adjudication, ECR posting) with owner and expiry | W | 1 | workflow |
| `POST /office/system/locks/{lockId}/release` 🔐 | Supervised release of an orphaned lock (reason required) → `LockReleased.v1` (tracker: "Unable to lock process", phantom "concurrent claims already under processing") | W | 1 | workflow |
| `POST /office/cases/{caseId}/documents/{docId}/attestation-views` | Record that the caseworker opened the employer-signed PDF / DSC document; enables the approve action (tracker: "View the employer signed pdf first") | W | 1 | workflow |


**Designed from the Samadhan Setu analysis** (not in the spec files; see `docs/samadhan-setu-mapping.md`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /office/claims/{claimId}/audit-trail` | Full claim audit trail for officers and auditors: transitions, actor IDs, approval level, rule version, lock events, CAD versions | W | 1 | claim |
| `GET /office/claims/{claimId}/additional-forms` | **Additional Form Details** — forms filed with a claim (e.g. a Joint Declaration): filed / initiated dates, processing status, rejection reason, pending office | W | 1 | claim |
| `GET /office/annexure-k-files?direction=` | **ANNEXURE K FILE** — Annexure K inward / outward between field offices for Form 13 transfers | W | 1 | claim |
| `POST /office/annexure-k-files/{annexureId}/reconciliations` 🔐 | **ANNEXURE K RECO** — match an inter-office Annexure K with the transfer and member records | W | 1 | claim |
| `POST /office/annexure-k-files/{annexureId}/vdr-reconciliations` 🔐 | **ANNEXURE K VDR RECO** — match the Annexure K amount with the VDR receipt | W | 1 | contribution |

## 9. Pension (EPS) and pensioners

`pension-service` holds seeded pensions in payment (mock CPPS credits), recomputes them when a published rule set changes the pension formula (revisions with arrears, approved by an APFC (Pension)), and serves the member's estimate and the public calculator under the formula in force. Everything else is planned.

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /pensioners/me/life-certificate` | **Jeevan Pramaan / Digital Life Certificate** status: last submitted, valid till, source | M | 1 | pension |
| `GET /pensioners/me` | Pensioner profile (PPO number, pension type, disbursing bank) | W | 1 | pension |
| `GET /pensioners/me/ppo` | **PPO** view / download | W | 1 | pension |
| `GET /pensioners/me/pension-slips?month=` | **Pension slip** | W | 1 | pension |
| `GET /pensioners/me/payments` | Pension payment history | W | 1 | pension |
| `POST /pensioners/me/life-certificate/submissions` | Record DLC submission (mock Jeevan Pramaan / face-auth adapter) | M | 1 | pension |
| `POST /integrations/mock-jeevan-pramaan/dlc-events` | Signed callback from mock Jeevan Pramaan | M | 1 | pension |
| `POST /pensioners/me/bank-change-requests` 🔐 | Change disbursing bank | W | 1 | pension |
| `POST /pensioners/me/declarations` | Non-remarriage / non-employment declarations | W | 1 | pension |
| `GET /office/pensions/life-certificates/overdue` | Pensioners with expired life certificates | W | 1 | pension |
| `POST /office/pensions/{ppoId}/suspensions` 🔐 | Suspend pension on missing life certificate | W | 1 | pension |
| `POST /office/pensions/{ppoId}/resumptions` 🔐 | Resume pension | W | 1 | pension |
| `GET /office/pensions/enquiries?ppo=&memberId=&uan=` | **Pension Enquiry Details** — PPO, beneficiaries, pension payments, scheme certificate issue, service, arrears adjustment, recovery and TDS (restricted to the officer's office) | W | 1 | pension |
| `POST /office/pensions/{ppoId}/updation-activities` 🔐 | DA (Pension) initiates an updation activity: `BASIC_DETAILS`, `PENSION_START`, `PENSION_STOP`, `DLC_REVALIDATION`, `UNHOLD_TRANSACTIONS` | W | 1 | pension |
| `GET /office/pensions/updation-activities?activity=&mode=&status=` | **Track Claim Updation Activity Status** — PRO and DA activities by filing mode (physical / online) and status (new, pending, rejected, settled, sent back to DA), transfer cases separately | W | 1 | pension |
| `POST /office/pensions/updation-activities/{activityId}/decisions` 🔐 | APFC (Pension) settles, rejects or sends back an updation activity (maker ≠ checker); a settled activity changes the pension (life certificate, start / stop, unhold, bank) | W | 1 | pension |
| `POST /office/physical-claims` (`formType=PPO_AMENDMENT_BENEFICIARY` \| `PPO_AMENDMENT_SERVICE` \| `PPO_AMENDMENT_POHW`) | PRO counter intake of a **PPO amendment** (beneficiary, service, pension on higher wages) | W | 1 | pension |
| `POST /office/physical-claims` (`formType=DEATH_UPDATION` \| `PHYSICAL_LC_UPDATION` \| `SPOUSE_REMARRIAGE_UPDATION`) | PRO counter intake of a pensioner **death**, **physical life certificate** or **spouse remarriage** updation | W | 1 | pension |
| `POST /office/pensions/ppo-issuances` 🔐 | Issue PPO after Form 10D settlement | W | 1 | pension |
| `GET /office/pension-claims?state=` | Pension claims (Form 10D) of the office by state: each desk sees what is waiting for it | W | 1 | pension |
| `POST /office/pensions/{ppoId}/revisions` 💰🔐 | Pension revision (incl. higher-pension outcome) | W | 1 | pension |
| `GET /office/pensions/revisions?state=` | Pension revisions proposed when a published formula change raises pensions in payment, with arrears to date | W | 1 | pension |
| `POST /office/pensions/higher-pension-options/{optionId}/decisions` 🔐 | Decide on a validated option → dues demand event | P | 3 | pension |
| `POST /office/pensions/higher-pension-options/{optionId}/ledger-transfers` 💰🔐 | PF→pension fund transfer after dues are paid → journal via `contribution-service` event | P | 3 | pension |

Pensioner grievances use the grievance endpoints in §13 with `category=PENSION`.


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /office/pension-claims/{claimId}/input-data-sheets` | DA (Accounts) prepares the Input Data Sheet (Claims > Transaction > Form-10D/10C) | W | 1 | pension |
| `POST /office/pension-claims/{claimId}/input-data-sheets/{idsId}/approvals` 🔐 | AO approves the IDS | W | 1 | pension |
| `POST /office/pensions/worksheets` | DA (Pension) generates the worksheet (Pension > Transaction > Pension Worksheet) | W | 1 | pension |
| `POST /office/pensions/worksheets/{worksheetId}/approvals` 🔐 | APFC (Pension) approves the worksheet | W | 1 | pension |
| `POST /office/pensions/special-10d-cases` | Special 10D module for incomplete service / wage data | P | 3 | pension |
| `POST /office/pensions/transfers-in` | Transfer in with / without PPO | W | 1 | pension |
| `POST /office/pensions/ppos/{ppoId}/initial-arrears` 💰 | Initial arrear (DA(P) → SS(P) → APFC(P)) | W | 1 | pension |
| `POST /office/pensions/ppos/{ppoId}/e-signatures` 🔐 | APFC (Pension) e-signs the PPO | W | 1 | pension |
| `POST /office/pensions/ppos/{ppoId}/dispatches` | Dispatch PPO and scroll | W | 1 | pension |
| `GET /office/pensions/disbursement-lists` | Legacy bank-wise disbursement lists (until CPPS) | P | 3 | pension |
| `POST /cpps/disbursement-runs` 💰🔐 | CPPS monthly pan-India disbursement run through the sponsor bank | W | 1 | pension |
| `GET /cpps/disbursement-runs` | CPPS runs with their paid statements and reconciliation exceptions | W | 1 | pension |
| `POST /cpps/reconciliations` 🔐 | CPPS reconciliation of paid statements | W | 1 | pension |
| `POST /integrations/mock-pension-bank/paid-statements` | Signed paid-statement callback from the pension bank | M | 1 | pension |
| `GET /ho/actuarial/extracts` | EPS data extract for actuarial valuation (no direct identifiers) | P | 3 | pension |


**Added from the Samadhan Setu integration spec** (`../samadhan-setu files/PF_LIFE_INTEGRATION_SPECIFICATION.md`, checked against the tracker issues)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /members/me/pension-eligibility-preview` | Pre-check pension eligibility across all member IDs under the UAN; flags untransferred service (threshold from illustrative config) | W | 1 | pension |
| `POST /office/pensions/service-aggregations` 🔐 | DA (Pension) aggregates untransferred past service into the calculation sheet | W | 1 | pension |
| `POST /members/me/pension-scheme-certificates/{certId}/surrenders` 💰🔐 | Surrender a Scheme Certificate to convert it to monthly pension (Form 10D) or withdrawal benefit (Form 10C) | W | 1 | pension |
| `POST /office/pensions/scheme-certificates/{certId}/surrender-adjudications` 🔐 | DA (Pension) validates and cancels a surrendered Scheme Certificate | W | 1 | pension |
| `POST /office/pensions/brs-reconciliations` 💰🔐 | Monthly Bank Reconciliation Statement (BRS) of pension scrolls vs bank debit advices | W | 1 | pension |

## 10. Compliance, e-proceedings and enforcement

`compliance-service` (planned, phase 2). CAIU risk signals (`init.md` §8.4) can open a case but never trigger a penalty automatically. Assessments emit `DemandRaised.v1`; payment happens through §5 demands.

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /caiu/synthetic-risk-signals` | CAIU risk signals (Journey D2) | W | 1 | intelligence |
| `POST /caiu/synthetic-risk-signals/{signalId}/reviews` | Investigator disposition (Journey D4) | W | 1 | intelligence |
| `GET /office/compliance/defaulters` | Non-filing / short-payment detection | W | 1 | reporting |
| `POST /office/compliance/cases` | Open proceeding / enforcement case | W | 1 | compliance |
| `GET /office/compliance/cases?type=&status=` | Case search | W | 1 | compliance |
| `GET /office/compliance/cases/{caseId}` | Case detail with full proceeding history | W | 1 | compliance |
| `POST /office/compliance/cases/{caseId}/notices` 🔐 | Issue and serve notice / summons | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/hearings` | Schedule / record hearing | P | 3 | compliance |
| `POST /employers/me/proceedings/{caseId}/submissions` | Employer reply / evidence submission | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/orders` 🔐 (`kind=7A`) | **7A** dues-determination order | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/orders` 🔐 (`kind=14B`) | **14B damages** order (illustrative formula) | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/orders` 🔐 (`kind=7Q`) | **7Q interest** order | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/reviews-7b` 🔐 | **7B** review of an order | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/escaped-assessments-7c` 🔐 | **7C** escaped-assessment proceeding | P | 3 | compliance |
| `POST /office/compliance/membership-disputes` 🔐 | **26B** coverage / membership dispute | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/appeals` | **7-I** appeal record (filed before the tribunal) | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/appeals/{appealId}/pre-deposits` 💰 | **7-O** pre-deposit evidence | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/appeals/{appealId}/pre-deposit-waivers` 🔐 | 7-O waiver / reduction decision record | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/recovery-8f` 🔐 | **8F** recovery / attachment (demo record only) | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/recovery-certificates` 🔐 | **8B–8E** recovery certificate execution (demo record only) | P | 3 | compliance |
| `POST /office/compliance/cases/{caseId}/prosecutions` 🔐 | Prosecution / legal referral record | P | 3 | compliance |
| `POST /office/compliance/inspections` | Inspection scheduling, including CAIU-allocated inspections | P | 3 | compliance |
| `POST /office/compliance/inspections/{inspectionId}/reports` | Enforcement officer inspection report | P | 3 | compliance |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /office/compliance/inspections/{inspectionId}/processing-notes` | DA (Compliance) processes the inspection report in the e-file | P | 3 | compliance |
| `POST /office/recovery/{caseId}/attachments` 🔐 | Attachment of movable / immovable property (demo record only) | P | 3 | compliance |
| `POST /office/recovery/{caseId}/sales` 🔐 | Sale of attached property (demo record only) | P | 3 | compliance |
| `POST /office/recovery/{caseId}/receivers` 🔐 | Appointment of receiver (demo record only) | P | 3 | compliance |
| `POST /office/recovery/{caseId}/arrest-warrants` 🔐 | Arrest and detention of defaulter (demo record only) | P | 3 | compliance |
| `POST /office/legal/cases` | Register a court / tribunal case | P | 3 | compliance |
| `GET /office/legal/cases` | Legal case register | P | 3 | compliance |
| `POST /office/legal/cases/{caseId}/orders` | Record a court / tribunal order | P | 3 | compliance |
| `GET /ho/reports/proceedings` | HO view of e-Proceedings (7A, 14B & 7Q, virtual hearings) | P | 3 | reporting |
| `GET /ho/reports/recovery` | HO recovery monitoring | P | 3 | reporting |


**Added from the Samadhan Setu integration spec** (`../samadhan-setu files/PF_LIFE_INTEGRATION_SPECIFICATION.md`, checked against the tracker issues)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /employers/me/vishwas-applications` 💰 | Apply under **VISHWAS** (one-time settlement of 14B damages / penalty disputes at reduced rates for past defaults) | W | 1 | compliance |
| `GET /employers/me/vishwas-applications` | The establishment's VISHWAS applications and its open 14B demands | W | 1 | compliance |
| `GET /office/compliance/vishwas-applications` | VISHWAS applications of the office's establishments | W | 1 | compliance |
| `POST /office/compliance/vishwas-applications/{applicationId}/decisions` 🔐 | Recalculate damages under VISHWAS and decide the application → `DemandRaised.v1` for the revised amount | W | 1 | compliance |

## 11. Exempted establishments (PF trusts)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /exempted/me/profile` | Trust profile and exemption conditions | P | 3 | employer |
| `POST /exempted/me/returns` | Periodic returns of exempted establishment | P | 3 | contribution |
| `GET /exempted/me/annexure-k-requests` | **Annexure K** requests from the field office (transfers in / out) | P | 3 | claim |
| `POST /exempted/me/annexure-k-submissions` 💰 | Submit Annexure K with the transfer amount | P | 3 | claim |
| `POST /office/exempted/annexure-k/{annexureId}/reconciliations` 🔐 | Match Annexure K to receipt / member records | P | 3 | claim |
| `POST /exempted/me/audits` | Annual trust audit filing | P | 3 | employer |
| `POST /exempted/me/surrender-requests` 🔐 | Surrender / cancellation of exemption | P | 3 | employer |
| `POST /office/exempted/{estId}/past-accumulation-transfers` 💰🔐 | Transfer past accumulations to EPFO after surrender / cancellation | P | 3 | contribution |
| `POST /office/exempted/past-accumulation-bulk-transfers` 💰🔐 | **PAST ACCUM BULK TRANSFER** — transfer past accumulations of many members in one batch | P | 3 | contribution |
| `POST /office/exempted/{estId}/past-accumulation-vdr-reconciliations` 🔐 | **PAST ACCUM VDR RECO** — match past-accumulation receipts with VDR entries | P | 3 | contribution |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /office/exempted/{estId}/returns` | Exemption cell reviews trust returns | P | 3 | contribution |
| `GET /office/exempted/{estId}/audits` | Exemption cell reviews trust audit reports | P | 3 | employer |
| `POST /ho/exemptions/{estId}/decisions` 🔐 | HO grants / cancels exemption | P | 3 | employer |


**Added from the Samadhan Setu integration spec** (`../samadhan-setu files/PF_LIFE_INTEGRATION_SPECIFICATION.md`, checked against the tracker issues)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /office/exempted/{estId}/past-accumulation-ingestions` 💰🔐 | Bulk-ingest member ledgers and past accumulations of a surrendered PF trust | W | 1 | contribution |

## 12. International workers

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `GET /members/me/international` | International worker profile | W | 1 | international |
| `POST /international/coc-applications` | Certificate of Coverage application (mock) | W | 1 | international |
| `GET /international/coc-applications/{id}` | CoC status | W | 1 | international |
| `GET /international/coc-applications` | The establishment's Certificate of Coverage applications | W | 1 | international |
| `GET /office/international/coc-applications` | Certificate of Coverage applications of the office's establishments | W | 1 | international |
| `POST /international/coc-applications/{id}/extensions` | CoC extension / renewal | W | 1 | international |
| `POST /office/international/coc-applications/{id}/decisions` 🔐 | IW cell verification and CoC issuance (mock) | W | 1 | international |
| `GET /international/agreements` | Social-security agreement catalogue (synthetic, labelled) | W | 1 | international |
| `POST /international/totalisation-claims` | Route a benefit claim under a social-security agreement | P | 3 | international |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /international/coc-applications/{id}/signed-uploads` | Employer uploads signed CoC application | W | 1 | international |
| `GET /international/coc-applications/{id}/certificate` | Download issued Certificate of Coverage | W | 1 | international |
| `GET /partners/foreign-agencies/coc-certificates/{id}` | Foreign agency verifies a CoC (FOREIGN AGENCIES login) | P | 3 | international |

## 13. Grievances, security, platform, audit and oversight

Monitoring (`/monitoring/**`), AI (`/ai/**`), audit (`/audit/**`) and NDC (`/ndc/**`) stay as listed in `init.md` §3.1, all **W**.

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /members/me/grievances` | Member registers grievance linked to a claim (Journey C1) | W | 1 | grievance |
| `GET /members/me/grievances` | List own grievances | W | 1 | grievance |
| `POST /grievances/{grievanceId}/documents` | Attach a synthetic document (object store, malware-scan stub, Journey C1) | W | 1 | grievance |
| `GET /grievances/{grievanceId}` | Grievance detail (only the assigned office can read the body — Journey C2) | W | 1 | grievance |
| `POST /grievances/{grievanceId}/messages` | Reply / message | W | 1 | grievance |
| `POST /grievances/{grievanceId}/evidence-links` | Officer attaches case-linked evidence (Journey C3) | W | 1 | grievance |
| `POST /grievances/{grievanceId}/escalations` | Escalate to next supervisory tier (Journey C4) | W | 1 | grievance |
| `POST /grievances/{grievanceId}/resolution` 🔐 | Resolve with reason (Journey C4) | W | 1 | grievance |
| `POST /grievances/{grievanceId}/reopen-requests` | Complainant requests reopening | W | 1 | grievance |
| `POST /grievances/{grievanceId}/reminders` | Complainant reminder on an overdue grievance | W | 1 | grievance |
| `POST /grievances/{grievanceId}/feedback` | Closure feedback / satisfaction | W | 1 | grievance |
| `GET /security/me/permissions` | Permission inspection | W | 1 | gateway |
| `GET /security/request-activity` | Security analyst view of recent API rates and redacted request activity (Redis POC, 24-hour retention) | W | 1 | gateway |
| `GET /security/sessions` | Session inspection (security analyst, interface 17) | W | 1 | gateway |
| `POST /security/sessions/{sessionId}/revocations` 🔐 | Revoke session (Journey A9) | W | 1 | gateway |
| `POST /security/step-up-challenges` | Start a demo step-up confirmation for a 🔐 action | W | 1 | gateway |
| `POST /security/step-up-challenges/{challengeId}/verifications` | Complete step-up | W | 1 | gateway |
| `POST /internal/security-events` | Ingest IdP events (login, new device, credential change) from the Keycloak event listener into audit + outbox → `SecurityEventRecorded.v1` (Journey D1). Service-to-service only | W | 1 | audit |
| `GET /hrm/me` | HRM staff profile and assignment metadata (interface 15) | W | 1 | workflow |
| `POST /vigilance/referrals` | Refer a confirmed risk signal, a member report or a complaint to vigilance (interface 18) | W | 1 | workflow |


**Added from the stakeholder activity map** (`docs/stakeholder-activities.yaml`)

| Method & path | Function | Status | Phase | Owner |
|---|---|---|---|---|
| `POST /grievances/{grievanceId}/office-transfers` | Transfer a grievance to another office | W | 1 | grievance |
| `POST /integrations/cpgrams/grievances` | CPGRAMS grievance feed (signed) | M | 3 | grievance |
| `POST /office/rti-requests/{requestId}/replies` | Record RTI replies | P | 3 | grievance |
| `POST /security/incidents` 🔐 | Record a security incident; report to CERT-In | W | 1 | audit |
| `GET /security/incidents` | Security incidents on record and their CERT-In reporting (mock) | W | 1 | audit |
| `GET /privacy/requests` | Data-principal requests queue (DPDP Act) | P | 3 | audit |
| `POST /privacy/requests/{requestId}/decisions` 🔐 | Decide a data-principal request | P | 3 | audit |
| `GET /vigilance/cases` | Vigilance case list (restricted: the CVO, or the zone the inquiry is assigned to) | W | 1 | workflow |
| `GET /vigilance/cases/{caseId}` | A vigilance case with its evidence and history (restricted; every read audited) | W | 1 | workflow |
| `POST /vigilance/cases/{caseId}/findings` 🔐 | Zonal vigilance reports the preliminary inquiry's findings | W | 1 | workflow |
| `POST /vigilance/cases/{caseId}/decisions` 🔐 | CVO / Director (Vigilance): assign an inquiry, or decide on the findings | W | 1 | workflow |
| `GET /vigilance/sensitive-posts` | Officers on sensitive posts, their tenure and who is due for rotation (P2.10b) | W | 1 | workflow |
| `POST /vigilance/clearances` | Ask for vigilance clearance for an officer (posting to a sensitive post, promotion, retirement, deputation, passport NOC) | W | 1 | workflow |
| `GET /vigilance/clearances` | Vigilance clearances issued (the CVO also sees what withheld them) | W | 1 | workflow |
| `GET /zo/fraud-risk/cases` | Zonal / regional fraud-risk committee case list | W | 1 | workflow |
| `POST /hrm/postings` 🔐 | Staff postings and role assignment to offices (drives jurisdiction) | W | 1 | workflow |
| `GET /audit/concurrent/extracts` | Concurrent Audit Cell daily functionality extract (Audit Portal) | W | 1 | audit |
| `POST /audit/concurrent/alerts` | Concurrent audit alert to an RO | W | 1 | audit |
| `POST /audit/concurrent/alerts/{alertId}/replies` | OIC replies to a concurrent-audit alert | W | 1 | audit |
| `GET /audit/concurrent/alerts` | Concurrent-audit alerts: the zone's (Audit Cell) or the office's (OIC), with overdue replies | W | 1 | audit |
| `POST /audit/internal/reports` | Internal audit report for an office | P | 3 | audit |
| `POST /audit/internal/reports/{reportId}/paras` | Raise an audit para | P | 3 | audit |
| `POST /audit/internal/paras/{paraId}/replies` | Office compliance reply to a para | P | 3 | audit |
| `POST /audit/internal/paras/{paraId}/decisions` 🔐 | Audit Division drops / keeps a para | P | 3 | audit |
| `GET /ho/finance/balance-sheet` | Balance sheet for statutory / attest audit (read-only) | P | 3 | reporting |
| `GET /ho/finance/investments` | Investment reporting | P | 3 | reporting |
| `POST /integrations/fund-managers/positions` | Fund manager / custodian position feed (signed) | M | 3 | reporting |
| `GET /governance/board-packs` | CBT / EC / FIAC board packs (aggregates only) | P | 3 | reporting |
| `GET /zo/dashboards` | Zonal comparison dashboard (interface 9, aggregated, read-only) | W | 1 | reporting |
| `GET /do/dashboards` | District dashboard (interface 7) | W | 1 | reporting |
| `GET /ho/config/rule-sets` | Policy administration: rule-set versions in force, scheduled, drafts and history | W | 1 | platform |
| `GET /ho/config/rule-sets/{versionId}` | One rule set: its checks, what changed from its base, and worked examples of the effect | W | 1 | platform |
| `POST /ho/config/rule-sets` | Draft a new rule-set version (wage ceilings, rates, claim types, approval matrix, auto-settlement, grievance settings) from an existing one, with an effective date | W | 1 | platform |
| `PUT /ho/config/rule-sets/{versionId}` | Edit a draft (If-Match) | W | 1 | platform |
| `POST /ho/config/rule-sets/{versionId}/submissions` | Submit a draft that passes every check for approval | W | 1 | platform |
| `POST /ho/config/rule-sets/{versionId}/decisions` 🔐 | Approve and publish (effective from its date), or return, a submitted rule set; approver ≠ drafter | W | 1 | platform |
| `GET /public/policy/current` | The rule set in force today: ceilings, rates, claim types and limits (public figures only) | W | 1 | platform |
| `POST /ho/circulars` | Publish a circular to the public corpus | W | 1 | intelligence |
| `GET /ndc/event-failures` | Failed events / DLQ view (interface 11) | W | 1 | platform |
| `POST /ndc/event-failures/{eventId}/replays` 🔐 | Replay a dead-lettered event (idempotent consumers) | W | 1 | platform |
| `POST /ndc/issue-tracker/requests` | Raise an Issue Tracker request (e.g. freeze / de-freeze), with the order attached | W | 1 | platform |
| `POST /ndc/issue-tracker/requests/{requestId}/executions` 🔐 | IS Division executes the block / unblock | W | 1 | platform |
| `GET /ndc/issue-tracker/requests` | Issue Tracker requests: all (IS Division) or the officer's own | W | 1 | platform |
| `GET /ndc/dr/replication-status` | ADC (DR site) replication status | P | 3 | platform |
| `POST /ndc/dr/failover-drills` 🔐 | Run a DR failover drill | P | 3 | platform |
| `POST /training/sandboxes` | Create a synthetic-data training sandbox (PDNASA / ZTI) | P | 3 | platform |

---

## 14. Event-only contracts these functions rely on

Added to `init.md` §7. These have no public endpoint but are required for the rows marked W.

| Event | Producer → consumers | Needed for |
|---|---|---|
| `SecurityEventRecorded.v1` | audit → intelligence, member (session history) | Journey D1–D2 |
| `PaymentInstructed.v1` | claim → payment-simulator | Journey B6 |
| `NotificationRequested.v1` | claim, payment-simulator, grievance → member (notifications projection) | Journey B7, C |
| `DemandRaised.v1` | compliance, pension → contribution (payable demands) | §5 demands (phase 2) |
| `LedgerReversed.v1` | contribution → reporting, audit | §5 reversals (phase 2) |
| `PaymentScrollGenerated.v1` | claim → payment-simulator | §8 scrolls (phase 2) |

## 15. Configuration each function needs

Every rule-dependent function reads a versioned, effective-dated rule set, all marked `ILLUSTRATIVE_ONLY`.
`config/demo-rules.yaml` is only the baseline; new versions are drafted, checked, approved (maker-checker) and
published in Policy administration (`/ho/config/rule-sets`), and each service applies the version in force on the
relevant date (claim date, ECR wage month) and records it with the decision.

| Config section | Used by |
|---|---|
| `contribution.components` (EPF, EPS, EDLI, admin charges — illustrative %) and a wage-ceiling placeholder | ECR, calculator |
| `ecr.types` — REGULAR, ARREAR, SUPPLEMENTARY | ECR |
| `demand.types` — DAMAGES_14B, INTEREST_7Q, ADMIN_CHARGES, HIGHER_PENSION_DUES | Demands |
| `payment.channels` — NET_BANKING, BANK_COUNTER (`definition_confirmed: false`) | Payment intents |
| `office_receipts.vdr_categories` (`definition_confirmed: false`) | VDR entries, VDR Special |
| `ledger_adjustments.types` — APPENDIX_E (`definition_confirmed: false`) | Office adjustments |
| `claims.form_types` with eligibility predicates, required documents, dual-control thresholds | Claims |
| `pension.life_certificate` (validity window, grace period — illustrative) | Pension |
| `pension.types` (member, widow, child, orphan …) | Pension, family pension |
| `interest.annual_rate` per financial year (illustrative) | Interest posting |
| `tax.tds` and taxable-interest thresholds (illustrative) | TDS, taxable-interest split |
| `compliance.damages_14b` / `interest_7q` formulas (illustrative) | Compliance orders |
| `establishment.exemption_statuses`, `coverage_types` | Establishment configuration |
| `security.step_up_required_for` — list of 🔐 actions | Gateway |

Anything with `definition_confirmed: false` (bank-counter/cash channel, VDR categories, VDR Special, Appendix E) stays disabled in the demo UI and shows a "definition pending" label.

## 16. Coverage summary

Counted from the tables above (one row = one operation).

| Domain | W | M | P | ? | Phase-1 rows | Total |
|---|---|---|---|---|---|---|
| Public information and establishment search | 6 | 1 | 12 | 0 | 7 | 19 |
| Establishment registration and configuration | 4 | 4 | 22 | 0 | 5 | 30 |
| Employer operators, signatories, DSC and e-sign | 6 | 2 | 2 | 0 | 6 | 10 |
| Employer-side member management | 1 | 1 | 24 | 0 | 1 | 26 |
| Returns, challans and payments | 9 | 4 | 15 | 7 | 13 | 35 |
| Member self-service | 10 | 4 | 17 | 0 | 10 | 31 |
| Member claims, transfers and pension applications | 5 | 0 | 15 | 0 | 5 | 20 |
| Office claim processing and member accounts | 8 | 0 | 21 | 0 | 8 | 29 |
| Pension (EPS) and pensioners | 0 | 4 | 26 | 0 | 1 | 30 |
| Compliance, e-proceedings and enforcement | 2 | 0 | 31 | 0 | 2 | 33 |
| Exempted establishments (PF trusts) | 0 | 0 | 11 | 0 | 0 | 11 |
| International workers | 0 | 3 | 7 | 0 | 0 | 10 |
| Grievances, security, platform, audit and oversight | 19 | 2 | 31 | 0 | 19 | 52 |
| **All** | **70** | **25** | **234** | **7** | **77** | **336** |

Every row is called by at least one activity in `docs/stakeholder-activities.yaml`; per-stakeholder API sets are generated into `docs/stakeholder-api-sets.md`. `docs/api-matrix.md` becomes the authoritative per-endpoint record once agents start building.
