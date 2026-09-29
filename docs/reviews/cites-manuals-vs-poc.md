<!-- Review of the CITES user manuals (../manuals, 24 .docx; text only, screenshots not extracted) against the POC as
of commit 5789611 (29 Sep 2026). Drafted by the Antigravity CLI (agy); every quoted manual phrase was checked
against the extracted text, and the statements about POC code were checked against the source. Known slip: §2.4
says multi-beneficiary payment was deferred to P2.6 — it has no slice yet. File links below point at the author's
checkout; read them as repo-relative paths. Follow-up: P2.5d in docs/phase-2-plan.md. -->

# EPFO POC vs. Official User Manuals: Comprehensive Review & Gap Analysis

This report evaluates the **EPFO Proof-of-Concept (POC)** codebase against the official **EPFO 2.01 / CITES User Manuals** across seven claim types and office processes:
1. **Form 19** (Final PF Settlement)
2. **Form 20** (PF Settlement on Death)
3. **Form 31** (PF Advance / Partial Withdrawal)
4. **Form 10C** (EPS Withdrawal Benefit & Scheme Certificate)
5. **Appendix E** (Field Office Member Balance & Ledger Adjustments)
6. **Form EDLI 5IF** (Employees' Deposit Linked Insurance Benefit)
7. **Physical Claim** (PRO Counter Intake & Diary)

---

## 1. Form 19 — Final PF Settlement

### 1.1 The Lifecycle in the Manual
* **Roles in Order**: 
  1. Member (`Form_19_User_Manual_-_Form_19_Claim_-_Member_2602.txt`)
  2. INITIATOR (`Form_19_User_Manual_-_Form_19_Claim-INITIATOR_2602.txt`)
  3. VERIFIER 1 (`Form_19_User_Manual_-_Form_19_Claim-VERIFIER_1_2602.txt`)
  4. VERIFIER 2 (`Form_19_User_Manual_-_Form_19_Claim-VERIFIER_2_2209.txt`)
  5. APPROVER (`Form_19_User_Manual_-_Form_19_Claim-APPROVER_2602.txt`)
* **Screens and Menu Paths**:
  * **Member**: Login with UAN, Password, Captcha, Mobile OTP. Homepage &rarr; `'Online Services'` &rarr; `'Claim (Form 31, 19& 10C)'`. Member enters `'Bank Account Number'` and clicks `'Verify'`, accepts Terms & Conditions pop-up (`'Yes'`), clicks `'Proceed for Online Claim'`, selects Form 19 from `'Select Claim Option'`, fills mandatory residential address, checks declaration, enters Aadhaar OTP, and downloads acknowledgement receipt.
  * **INITIATOR**: Login (User ID, Password, Captcha) &rarr; Top menu `'Claim'` &rarr; Dropdown `'Form 19 Claim'`. List displays: `Tracking ID`, `Member ID`, `UAN`, `Member Name`, `Processing Status`, `Remarks`. Fresh claims highlighted in green with status `'New'`.
  * **VERIFIER 1**: Top menu `'Claim'` &rarr; Dropdown `'Form 19 Claim'`. Shows claims forwarded from INITIATOR. List displays: `Tracking ID`, `Member ID`, `UAN`, `Member Name`, `Processing Status (Forwarded by INITIATOR)`, `Reports`.
  * **VERIFIER 2**: Top menu `'Claim'` &rarr; Dropdown `'Form 19 Claim'`. Shows claims forwarded from Verifier 1.
  * **APPROVER**: Top menu `'Claim'` &rarr; Dropdown `'Form 19 Claim'`. Shows claims forwarded from VERIFIER 2 or VERIFIER 1. List includes `Claim Amount` and status `Forwarded by VERIFIER 2/VERIFIER`.
* **States / Statuses**:
  * Manual mentions: `'New'`, `'Forwarded by INITIATOR'`, `'Forwarded by VERIFIER 2/VERIFIER'`, `'Operative'`, `'Inoperative'`, `'Dormant'`, `'Stopped Claims'`, `'Pending Claims'`.
  * Member side: "not stated in manual" (manual mentions "final claim is successfully submitted in the system" and acknowledgement receipt with claim reference number).
* **Key Checks Performed**:
  * **Member**: Bank account verification, mandatory residential address, Aadhaar declaration checkbox.
  * **INITIATOR**: Scrutiny of member details and bank account. Sets Account Status (`Operative`, `Inoperative`, `Dormant`). Action History review via `'View'` button. Mandatory CAD generation. Start-Stop claim: *"On clicking 'Stop Claim Processing' the INITIATOR is shown a pop-up where they are supposed to update the reason for Stopping the claim processing... This moves the claim to the list of Stopped Claims... In order to restart the claim, the INITIATOR needs to click on 'Restart Claim'... Once Confirmed by clicking 'Start' the claim moves back to the Pending Claims list"* (`Form_19_User_Manual_-_Form_19_Claim-INITIATOR_2602.txt`). Mandatory remarks, mobile OTP validation.
  * **VERIFIER 1**: Checks Member Info (UAN, Name, DOJ, DOL), KYC Compliance (PAN, Bank), CAD generated earlier, Initiator remarks, Action History. Verifies Initiator's Account Status selection. Regenerates CAD: *"After completing the verification of member and financial details, the verifier 1 must generate the Claim Approval Docket (CAD) once again. This step is mandatory before proceeding with approval or rejection"* (`Form_19_User_Manual_-_Form_19_Claim-VERIFIER_1_2602.txt`).
  * **VERIFIER 2**: Checks Reason for Leaving, KYC, prior remarks, regenerates CAD.
  * **APPROVER**: In-depth review: accuracy of earlier scrutiny, financial correctness, eligibility (service period, claim reason, account status), tax compliance, CAD completeness. Regenerates CAD. Mandatory remarks, mobile OTP validation.
* **Documents**:
  * Member acknowledgement receipt.
  * Internal: Claim Approval Docket (CAD) generated/regenerated at each level and downloadable as PDF/document.
* **Rejection / Return Paths**:
  * Initiator: Can choose `'Recommend to Reject'`.
  * Verifier 1: Reject is *"Not applicable, as per hierarchy. Rejection can only be done by Approver or by the Guidelines provided by EPFO"* (`Form_19_User_Manual_-_Form_19_Claim-VERIFIER_1_2602.txt`).
  * Verifier 2: Can choose `'Recommend to Reject (Send back to first level in case of final stage)'` which *"sends the claim back to the first level"* (`Form_19_User_Manual_-_Form_19_Claim-VERIFIER_2_2209.txt`).
  * Approver: Can choose `'Reject'` &rarr; *"Rejected claims &rarr; Sent back to the member with rejection remarks"* (`Form_19_User_Manual_-_Form_19_Claim-APPROVER_2602.txt`).
* **What Triggers Payment**:
  * Manual states claim is *"Finally approved by APPROVER"* or finally approved at Verifier 1 / Verifier 2 level if within financial delegation limit. Cash section payment scroll or dispatch mechanism is "not stated in manual".

### 1.2 How the POC Implements It
* **Claim Type & Rules**: Configured in [`config/demo-rules.yaml`](config/demo-rules.yaml#L38-L51) as `FINAL_SETTLEMENT`, form `"19"`, `requires_exit_months: 2`, `auto_settle_up_to_paise: 10000000`. Eligibility evaluated in [`services/claim-service/app/domain/claims.py:eligibility()`](services/claim-service/app/domain/claims.py#L63-L99).
* **Member Submission**: [`services/claim-service/app/api/routes.py:create_claim()`](services/claim-service/app/api/routes.py#L156-L214) (`POST /api/v1/members/me/claims`) creates claim in `AWAITING_CONFIRMATION`. Confirmed via [`confirm_claim()`](services/claim-service/app/api/routes.py#L216-L254) (`POST /api/v1/members/me/claims/{claim_id}/confirmations`), transitioning to `SUBMITTED` &rarr; `AUTO_APPROVED` (if amount &le; limit) or `UNDER_REVIEW`.
* **Office Adjudication**: Handled in [`services/workflow-service/app/api/routes.py`](services/workflow-service/app/api/routes.py):
  * DA recommends via [`recommend()`](services/workflow-service/app/api/routes.py#L207-L226) (`POST .../recommendations`).
  * First decision via [`first_decision()`](services/workflow-service/app/api/routes.py#L228-L232) (`fo.ss` or `fo.ao`).
  * Second approval via [`second_approval()`](services/workflow-service/app/api/routes.py#L234-L238) (`fo.apfc` or `fo.oic`).
* **CAD Generation**: [`services/claim-service/app/api/lifecycle_routes.py:generate_cad()`](services/claim-service/app/api/lifecycle_routes.py#L126-L150) (`POST /api/v1/office/claims/{claim_id}/cad`). Implemented exclusively for `fo.fa_accounts` (Accounts Wing F&A) **only after** the claim is in state `APPROVED` or `AUTO_APPROVED`.
* **Payment**: Instructed by `fo.cash` via [`services/claim-service/app/api/routes.py:payment_instruction()`](services/claim-service/app/api/routes.py#L348-L355) and batched into scrolls via [`services/claim-service/app/api/lifecycle_routes.py:generate_scroll()`](services/claim-service/app/api/lifecycle_routes.py#L170-L200).

### 1.3 Gaps (Manual vs. POC)
* **HIGH — CAD Timing and Role Inversion**: The manual defines CAD as the **"Claim Approval Docket"**, generated and regenerated sequentially by the INITIATOR, VERIFIER 1, VERIFIER 2, and APPROVER *during* claim scrutiny before approving or forwarding. In the POC, CAD is treated as a **"Claim Authorization Document"** generated by a separate persona (`fo.fa_accounts`) *after* final approval and before cash section payment.
* **HIGH — 3-Tier Verifier Hierarchy vs. Fixed 2-Step Chain**: Manual specifies INITIATOR &rarr; VERIFIER 1 &rarr; VERIFIER 2 &rarr; APPROVER, where VERIFIER 1 or 2 can give final approval if within financial limit, or forward upward. The POC implements a rigid linear chain (`fo.da_accounts` &rarr; `fo.ss`/`fo.ao` &rarr; `fo.apfc`/`fo.oic`).
* **HIGH — Start-Stop Claim**: Manual provides explicit `"Stop Claim Processing"` with a mandatory reason pop-up moving the claim to a `"Stopped Claims"` list, and `"Restart Claim"` returning it to pending. The POC has no claim-level stop/restart mechanism (only account-level freeze).
* **MEDIUM — Rejection Routing to First Level**: When Verifier 2 recommends rejection, manual states it *"sends the claim back to the first level"*. In the POC, any checker calling `REJECT` immediately sets `state="REJECTED"` and terminates the claim.
* **MEDIUM — Account Status Classification**: Manual mandates selecting and verifying `Account Status (Operative, Inoperative, Dormant)`. POC calculates inoperativeness in `contribution-service` but lacks explicit operative/dormant classification in the claim review screen.
* **LOW — Address Capture on Member Filing**: Manual requires mandatory residential address. POC `ClaimInput` accepts only account link, type, and amount.

### 1.4 Things the POC Does That the Manual Does Not Describe
* **Automatic Settlement**: POC settles claims &le; ₹1,00,000 automatically (`AUTO_APPROVED`) without officer intervention. Manual describes manual adjudication by officers for all claims.
* **TDS Deduction Calculation**: Dynamic tax deduction at source on payment date with Form 15G/15H waiver ([`lifecycle_routes.py:work_out_tax()`](services/claim-service/app/api/routes.py#L273-L286)).
* **Payment Scroll & Re-Disbursement**: Batch scrolls, mock bank return simulation, penny-drop validation, and APFC re-payment approval.
* **Member Claim Cancellation**: Member can cancel an unsettled claim before decision ([`lifecycle_routes.py:cancel()`](services/claim-service/app/api/lifecycle_routes.py#L86-L98)).

### 1.5 Concrete, Prioritised Recommendations
1. **[services/claim-service/lifecycle_routes.py]**: Redefine CAD as Claim Approval Docket and make it viewable/generable by dealing assistants and verifiers during review.
2. **[services/claim-service/routes.py]**: Add `STOPPED` state and endpoints `POST .../stop` and `POST .../restart` with audit reason.
3. **[services/workflow-service/engine]**: Route intermediate verifier rejection recommendations back to the Initiator rather than executing final rejection.
4. **[services/claim-service/routes.py]**: Add residential address field to `ClaimInput` and validate non-empty string.

---

## 2. Form 20 — PF Settlement on Death

### 2.1 The Lifecycle in the Manual
* **Roles in Order**: 
  1. Member Beneficiary / Claimant (`Form_20_Form_20_Death_Claim_-_MEMBER_V1.0.txt`)
  2. INITIATOR (`Form_20_Form_20_Death_Claim_-_INITIATOR_V1.0_-.txt`)
  3. VERIFIER (`Form_20_Form_20_Death_Claim_-_VERIFIER_V1.0.txt`)
  4. APPROVER (`Form_20_Form_20_Death_Claim_-_APPROVER_V1.0_-.txt`)
* **Screens and Menu Paths**:
  * **Member Beneficiary**: Member portal banner &rarr; Link `'EPFO Member Beneficiary – Method for claim filing'` at bottom banner. Enters member UAN, Beneficiary Aadhaar, Name, DOB, Captcha &rarr; `'Get Authorisation Pin'` &rarr; OTP &rarr; `'Validate OTP and Proceed'`. Beneficiary sees options: `File a New Claim` & `View filed Claims`.
  * **Filing Form 20**: Displays service details with option: *"Updating Date of Death (if not available) and Selecting type of Claim"*. Beneficiary selects `'PF Withdrawal Claim (Form 20)'`. Enters mandatory details: `Mobile No.`, `Address for communication`, `Bank Details`, `Death Certificate of member`, `Bank Account proof`, `Date of Birth proof of beneficiary`. Aadhaar consent &rarr; OTP &rarr; Submit. Success screen displays request to e-sign: *"E-signing the Submitted Claim"*. After e-signing, clicks `'View Claim PDF'`.
  * **Field Office**: Top menu `'Claim'` &rarr; Dropdown `'Form 20 Claim'`. Displays: `Tracking ID`, `Member ID`, `UAN`, `Member Name`, `Processing Status`, `View Reports`.
* **States / Statuses**:
  * Fresh claims highlighted in green. Processing status updated as forwarded. Account status: `Operative / Inoperative / Dormant`.
  * Decisions: Initiator/Verifier choose `Recommend to Approve` or `Recommend to Reject`. Approver chooses `Approve`, `Reject`, or `Send back to Initiator/First Level`.
  * Manual rule: *"Note- If Verifier took action like 'Recommend to Approve' then 'Approve' & 'Send Back to First Level/Initiator' options will be visible at Apporver level. Note- If Verifier took action like 'Recommend to Reject' then 'Reject' & 'Send Back to First Level/Initiator' options will be visible at Apporver level"* (`Form_20_Form_20_Death_Claim_-_APPROVER_V1.0_-.txt`).
* **Key Checks Performed**:
  * Scrutiny of member details and service history, Beneficiary Details, Bank account details of claimant, Claimant Details & Enclosures (Aadhaar Card, Death certificate), Account status verification. Review CAD (accuracy, PF balance, interest, completeness). Mandatory remarks and mobile OTP at all stages.
* **Documents**:
  * Death Certificate of member, DOB proof of beneficiary, Bank Account proof. E-signed claim PDF. CAD docket.
* **Rejection / Return Paths**:
  * Approver can reject or select `'Send back to Initiator/First Level'`.
* **What Triggers Payment**:
  * Manual states: *"the claim has moved to the next stage of processing claimant amount"* (`Form_20_Form_20_Death_Claim_-_APPROVER_V1.0_-.txt`). Further cash steps not stated in manual.

### 2.2 How the POC Implements It
* **Filing**: Handled in [`services/claim-service/app/api/death_routes.py:file_death_claim()`](services/claim-service/app/api/death_routes.py#L59-L121) (`POST /api/v1/claimants/death-claims`) for `form_type="FORM_20"`. Validates claimant against `nominations` table; checks `account["deceased_on"]` is recorded; creates claim in `SUBMITTED`, sets beneficiaries from e-nomination, transitions to `UNDER_REVIEW`.
* **Beneficiary Management**:
  * Claimant can add co-beneficiaries via [`add_beneficiary()`](services/claim-service/app/api/death_routes.py#L137-L151) (`POST .../beneficiaries`).
  * APFC amends shares via [`amend_share()`](services/claim-service/app/api/death_routes.py#L164-L190) (`PUT .../shares`).
* **Office Review & Payment**: Handled through standard workflow. Cashier cannot pay until shares total 100% ([`services/claim-service/app/api/routes.py:_instruct()`](services/claim-service/app/api/routes.py#L289-L294)). Navigation configured for `claimant` persona in [`apps/web/src/data/navigation.ts:CLAIMANT`](apps/web/src/data/navigation.ts#L99-L103).

### 2.3 Gaps (Manual vs. POC)
* **HIGH — Beneficiary Portal Authentication**: Manual defines a specialized login mechanism on the member portal (Member UAN + Beneficiary Aadhaar, Name, DOB + Aadhaar OTP). In the POC, `navigation.ts` states *"no portal login exists (claims are filed on paper or via UMANG)"* and provides a generic Keycloak `claimant` persona.
* **HIGH — Claimant Enclosure Uploads & E-Sign**: Manual requires uploading Death Certificate, Bank proof, and DOB proof, followed by Aadhaar e-sign. In POC, `DeathClaimInput` takes only UAN and beneficiary array—no document attachments or e-signature during submission.
* **HIGH — Updating Date of Death**: Manual allows the beneficiary to update Date of Death if not recorded. In POC, if employer has not marked date of death, filing fails with 422 `/problems/death-not-recorded`.
* **MEDIUM — Approver Conditional Button Visibility**: Manual strictly enforces that Approver sees `Approve` & `Send Back` if Verifier recommended approval, or `Reject` & `Send Back` if Verifier recommended rejection. POC presents static options.
* **LOW — Navigation Structure**: Manual uses `'Claim'` &rarr; `'Form 20 Claim'` with `'View Reports'` and green highlighting. POC uses generic `/office/work-queue`.

### 2.4 Things the POC Does That the Manual Does Not Describe
* Dedicated APFC Beneficiary Share Amendment tool (`PUT .../shares`) with reasons (`NOMINEE_DECEASED`, `COURT_ORDER`, `LEGACY_SETTLEMENT_OFFSET`, `GUARDIAN_APPOINTMENT`, `ADDED_HEIR`) and enforcement that shares total 100% before cashier can instruct payment.
* Single payment instruction issuing the full amount to one account (POC defers multi-account disbursement to P2.6).

### 2.5 Concrete, Prioritised Recommendations
1. **[apps/web, claim-service]**: Implement the Member Beneficiary Login (Member UAN + Beneficiary Aadhaar/DOB + Aadhaar OTP) as specified in `Form 20 Death Claim - MEMBER_V1.0.txt`.
2. **[services/claim-service/death_routes.py]**: Allow claimant to input Date of Death and upload Death Certificate during Form 20 submission when not previously recorded.
3. **[services/workflow-service/routes.py]**: Restrict Approver action choices based on previous Verifier recommendation.

---

## 3. Form 31 — PF Advance / Partial Withdrawal

### 3.1 The Lifecycle in the Manual
* **Roles in Order**: 
  1. Member (`Form_31_User_Manual_-_Form_31_Claim_-Member_2602.txt`)
  2. INITIATOR (`Form_31_User_Manual_-_Form_31_Claim-INITIATOR_2602.txt`)
  3. VERIFIER 1 (`Form_31_User_Manual_-_Form_31_Claim-VERFIER_1_2602.txt`)
  4. VERIFIER 2 (`Form_31_User_Manual_-_Form_31_Claim-VERIFIER_2.txt`)
  5. VERIFIER 3 (`Form_31_User_Manual_-_Form_31_Claim-VERIFIER_3.txt`)
  6. APPROVER (`Form_31_User_Manual_-_Form_31_Claim-APPROVER_2602.txt`)
* **Screens and Menu Paths**:
  * **Member**: Homepage &rarr; `'Online Services'` &rarr; `'Claim (Form 31, 19& 10C)'`. Bank account check &rarr; T&C pop-up &rarr; Member Details &rarr; `'Proceed for Online Claim'`. Dropdown `'Select Claim Option'` &rarr; Dropdown `'Select Service'` &rarr; Dropdown `'Purpose for which claim is required'`: *"All eligible purposed will be shown in the white colour while non-eligible purposes will be shown in the red colour"* (`Form_31_User_Manual_-_Form_31_Claim_-Member_2602.txt`). Eligible amount displayed; amount entered must be &le; eligible amount. Mandatory address details, declaration checkbox, Aadhaar OTP, acknowledgement receipt.
  * **INITIATOR**: Top menu `'Claim'` &rarr; Dropdown `'Form 31 Claim'`. Tracking ID opens claim. Scrutiny of member details and bank account. Account Status update (`Operative`, `Inoperative`, `Dormant`). Action History, CAD generation. Mandatory remarks, OTP validation. Start-Stop claim: *"Stop Claim Processing"* and *"Restart Claim"*.
  * **VERIFIER 1**: Top menu `'Claim'` &rarr; Dropdown `'Form 31 Claim'`. Scrutiny of advance reason, amount, purpose, account status. Mandatory CAD generation. Decision: `Approve` (for Operative up to threshold), `Recommend to Approve (Forward)` (to Verifier 2), `Reject` ("Not applicable, as per hierarchy"). Mandatory remarks, OTP.
  * **VERIFIER 2**: Reviews claim details, regenerates CAD. Decision: `Recommend to Approve` or `Recommend to Reject (Send back to first level in case of final stage)`.
  * **VERIFIER 3**: Reviews claim details, regenerates CAD. Decision: `Approve` (within powers &rarr; settlement stage for payment), `Recommend to Approve (Forward)` (to Approver), `Reject` ("Not applicable... Redirected to INITIATOR's worklist, who must re-forward it upward as 'recommend reject'").
  * **APPROVER**: Highest authority. Scrutinizes claim and CADs from prior levels, regenerates CAD. Decision: `Approve` or `Reject`.
* **States / Statuses**:
  * Fresh in green (`'New'`), `'Forwarded by INITIATOR'`, `'Forwarded by VERIFIER 1/2/3'`, `'Operative'`, `'Inoperative'`, `'Dormant'`, `'Stopped Claims'`, `'Pending Claims'`, Approved (moves to settlement stage), Rejected.
* **Key Checks Performed**:
  * Member selects Service and Purpose; system shows eligible in white, ineligible in red; enforces claim amount &le; eligible limit; mandatory residential address; Aadhaar OTP.
  * Office verifies purpose eligibility, past advances, service length, balance, CAD, mandatory remarks, mobile OTP.
* **Rejection / Return Paths**:
  * **Special Rejection Workflow**: All Form 31 manuals include this mandatory rule:
    > *"Special Note: Rejection Workflow in Claims: No processing functionary at the initiating or verifying levels has the authority to finalise a rejection. Once a rejection is recommended at any intermediate level, the claim is returned by the system to the originating worklist for further action. The originating functionary must re-forward the claim with the status 'Recommend to Reject'... after which the claim is routed upward in accordance with EPFO's prescribed approval hierarchy. The final authority for approving claim rejections is determined by EPFO as per the applicable approval matrix"* (`Form_31_User_Manual_-_Form_31_Claim-VERFIER_1_2602.txt`).
* **What Triggers Payment**:
  * Manual states: *"If the claim is approved within their powers, it is marked as approved and moves to the settlement stage for payment to the member"* (`Form_31_User_Manual_-_Form_31_Claim-VERIFIER_3.txt`).

### 3.2 How the POC Implements It
* **Configuration**: Baseline rules in [`config/demo-rules.yaml`](config/demo-rules.yaml#L30-L37) configure `ADVANCE_ILLNESS` (Form 31, medical advance), `requires_active_employment: true`, `max_from: employee_share`, `cap_paise: 100000000`, `auto_settle_up_to_paise: 10000000`.
* **Member Journey**: Member selects advance on `/member/claims`, enters amount, confirms with simulated one-time code ([`services/claim-service/app/api/routes.py:confirm_claim()`](services/claim-service/app/api/routes.py#L216-L253)).
* **Adjudication**: Dealing assistant recommends; SS or AO approves; APFC gives second approval if amount exceeds band ([`services/workflow-service/app/api/routes.py`](services/workflow-service/app/api/routes.py)).
* **Payment**: Cashier instructs payment via [`payment_instruction()`](services/claim-service/app/api/routes.py#L348-L355).

### 3.3 Gaps (Manual vs. POC)
* **HIGH — Rejection Loop to Initiator Worklist**: Manual explicitly specifies that intermediate verifier rejection recommendations **must return to the Initiator worklist** for re-forwarding upward with findings. In the POC, any officer calling `REJECT` immediately terminates the claim.
* **HIGH — Verifier 3 Tier**: Form 31 manual defines a 3rd Verifier tier (`VERIFIER 3`) for high-value advances. The POC engine supports at most two checker levels (`FIRST_CHECKERS`: SS/AO, `SECOND_CHECKERS`: APFC/OIC).
* **HIGH — CAD during Scrutiny**: Verifier 1, 2, 3, and Approver must generate/regenerate CAD before acting. In POC, CAD exists only post-approval via F&A wing.
* **HIGH — Start-Stop Claim**: Missing from Initiator role in POC.
* **MEDIUM — Purpose Hierarchy & Color Coding**: Manual requires selecting Service then Purpose (white for eligible, red for ineligible). POC supports only a single hardcoded advance type (`ADVANCE_ILLNESS`) in baseline configuration.
* **LOW — Minimum ₹1,000 Floor**: Manual requires minimum ₹1,000. POC checks `amount_paise > 0`.

### 3.4 Things the POC Does That the Manual Does Not Describe
* Automatic settlement up to ₹1,00,000 without human intervention.
* Member self-service claim cancellation (`POST .../cancellations`).
* Cash section payment scroll generation and bank return reconciliation.

### 3.5 Concrete, Prioritised Recommendations
1. **[services/workflow-service/routes.py]**: Implement the intermediate rejection loop: route `REJECT` recommendations from verifiers back to `fo.da_accounts` as `RECOMMEND_TO_REJECT`.
2. **[config/demo-rules.yaml]**: Expand Form 31 types to include Housing, Marriage, and Natural Calamity with respective eligibility criteria.
3. **[services/workflow-service]**: Support a 3rd Verifier tier in the YAML process definition and approval bands.

---

## 4. Form 10C — EPS Withdrawal Benefit & Scheme Certificate

### 4.1 The Lifecycle in the Manual
* **Roles in Order**: 
  1. Member (`Form-10C_User_Manual_-_Form_10C_-_Member2602.txt`)
  2. INITIATOR (`Form-10C_User_Manual_-_Form_10_C_Claim-INITIATOR_2602.txt`)
  3. VERIFIER / APPROVER (`Form-10C_User_Manual_-_Form_10_C_Claim-VERIFIER-APPOVER.txt`)
* **Screens and Menu Paths**:
  * **Member**: Login (UAN, Password, Aadhaar-linked OTP) &rarr; Homepage &rarr; `'Online Services'` &rarr; `'Claim (Form-31, 19& 10C)'`. Bank account check &rarr; Undertaking &rarr; `'Proceed to Online Claim'`. Under *"I want to apply for"*, selects `PENSION WITHDRAWAL BENEFIT (Form 10C)`. System displays NCP Days, Reason for Exit, and all member IDs. Consent box &rarr; `'Get Aadhaar OTP'` &rarr; `'Validate OTP and Submit Claim'` &rarr; Claim Reference Number (CRN) generated &rarr; `'CLICK HERE'` to view PDF.
  * **INITIATOR**: Top menu `'Claim'` &rarr; Dropdown `'Form 10 C'`. List displays: `Tracking ID`, `Member ID`, `UAN`, `Member Name`, `Type of Claim (Withdrawal Benefit / Scheme Certificate)`, `Processing Status`, `Remarks`. New claims in green. Reviews EPS membership, DOJ, Date of Exit, total EPS service, NCP days, original wages. Action History. Decision: `Recommend to Approve` or `Recommend to Reject`. Mandatory remarks, Submit. Start-Stop claim: clicks `"manage claim"` &rarr; `"Stop claim"` &rarr; reason &rarr; moves to Stopped Claims; Restart Claim returns to Pending.
  * **VERIFIER / APPROVER**: Top menu `'Claim'` &rarr; Dropdown `'Form 10 C'`. Reviews EPS status, service period, previous EPS claims or certificates, Action History.
    * Return rule: *"If Approver/verifier are not agreed with original wages, He can send back to DA for wage details corrections"* (`Form-10C_User_Manual_-_Form_10_C_Claim-VERIFIER-APPOVER.txt`).
    * Decision: `Recommend to Approve` or `Recommend to Reject`. Mandatory remarks. Submit &rarr; forwarded to higher authority if required basis claim amount and approval hierarchy.
* **States / Statuses**:
  * Member: CRN generated, Claim Successfully Submitted, View PDF.
  * Office: `'New'` (green), Processing Status, `Type of Claim (Withdrawal Benefit / Scheme Certificate)`. Decision: `Recommend to Approve`, `Recommend to Reject`, `Send back to DA for wage details corrections`.
* **Key Checks Performed**:
  * Member: Bank account, NCP days, Reason for Exit, Aadhaar OTP.
  * Office: EPS membership, service period (< 10 years for withdrawal benefit; &ge; 10 years requires Scheme Certificate/Pension), NCP days deduction, original wage details, previous EPS certificates.
* **Documents**:
  * Member: Undertaking, Claim PDF.
  * Office: Action history log, wage records, service ledger.
* **Rejection / Return Paths**:
  * Initiator/Verifier recommend rejection. Manual explicitly provides: *"He can send back to DA for wage details corrections"*.
* **What Triggers Payment**:
  * Manual states: *"The claim is officially forwarded to the next authority if required basis the claim amount and as per the defined approval hiearchy"* (`Form-10C_User_Manual_-_Form_10_C_Claim-VERIFIER-APPOVER.txt`). Payment trigger is not stated in manual.

### 4.2 How the POC Implements It
* **Cash Withdrawal Benefit**: Marked as Planned in [`docs/endpoint-catalogue.md`](docs/endpoint-catalogue.md#L37) (`POST /members/me/claims formType=FORM_10C, P | 2 | claim`). Omitted from `claims.types` in [`config/demo-rules.yaml`](config/demo-rules.yaml). **Not implemented.**
* **Scheme Certificate**: Implemented in [`services/pension-service/app/api/settlement_routes.py:request_certificate()`](services/pension-service/app/api/settlement_routes.py#L148-L165) (`POST /api/v1/members/me/pension-scheme-certificates`). Generates certificate instantly: *"Form 10C option: keep pension service for later instead of withdrawing it (illustrative: issued at once)"*.
* **Pre-flight**: [`services/claim-service/app/api/lifecycle_routes.py:eligibility_preview()`](services/claim-service/app/api/lifecycle_routes.py#L42-L57) accepts `formType="10C"` but returns no available types.

### 4.3 Gaps (Manual vs. POC)
* **HIGH — Missing Form 10C Withdrawal Benefit (Cash Claim)**: Completely absent from POC runtime claims engine.
* **HIGH — Scheme Certificate Bypasses Office Adjudication**: Manual mandates that Scheme Certificates undergo Initiator and Verifier/Approver scrutiny (service period, NCP days, wages). POC issues certificates instantaneously upon member request without office review.
* **HIGH — Send Back to DA for Wage Corrections**: Manual specifies that if Approver/Verifier disagree with wages, they return the claim to DA for wage corrections. POC workflow has no wage-correction return loop.
* **MEDIUM — NCP Days Tracking**: Manual verifies Non-Contributing Period (NCP) days to adjust eligible EPS service. POC calculates service purely from calendar dates.

### 4.4 Things the POC Does That the Manual Does Not Describe
* Surrender and aggregation of Scheme Certificates during Form 10D pension settlement ([`settlement_routes.py:add_past_service()`](services/pension-service/app/api/settlement_routes.py#L168-L185)).

### 4.5 Concrete, Prioritised Recommendations
1. **[config/demo-rules.yaml, claim-service]**: Add `PENSION_WITHDRAWAL` (Form 10C) to claim types with statutory table (Table D factor &times; exit wage).
2. **[services/pension-service/settlement_routes.py]**: Route Scheme Certificate requests through DA &rarr; AO review rather than instant issuance.
3. **[services/member-service]**: Track NCP days on member service records and deduct from pensionable service.

---

## 5. Appendix E — Office Member Ledger Adjustments

### 5.1 The Lifecycle in the Manual
* **Roles in Order**: 
  1. INITIATOR (`Form_Appendix_E_User_Manual_-_Form_Appendix_E-INITIATOR.txt`)
  2. VERIFIER / APPROVER (`Form_Appendix_E_User_Manual_-_Form_Appendix_E-VERIFIER_APPROVER.txt`)
  *(Internal field office function; never filed by a member).*
* **Screens and Menu Paths**:
  * **INITIATOR**: Login (User ID, Password, Captcha) &rarr; Home Page &rarr; List at bottom left &rarr; `'Appendix E'`. Search by `UAN` or `Member ID`. Selecting Member ID shows Establishment ID, Establishment Name, Member Name, and Type of Appendix E form. Initiator reviews member ledger, selects Appendix E type, edits balances, attaches Notesheet, enters `Notesheet Number`, `Date`, and `Remarks`, and clicks `'Submit'`. System displays Appendix E Report (`Tracking ID`, `Transaction ID`, PDF of changes). Initiator views PDF and clicks `'Submit'` to forward to Verifier/Approver.
  * **VERIFIER / APPROVER**: Home Page &rarr; List at bottom left &rarr; `'Appendix E'`. Tabular list of forms forwarded by Initiator (newly transferred highlighted in green). Selects Member ID &rarr; reviews updated details and Appendix E report PDF &rarr; provides final recommendations for processing.
* **The 4 Appendix E Types in Manual**:
  1. `'Other Appendix E'`: *"used to edit both Employer (Taxabe and Non-Taxable), Employee Share Balances and EPS Balance"*
  2. `'Transfer in Interest, MO Return Interest, ECS Return Interest, NEFT Return Interest and Cheque Return Interest Appendix E'`: *"allows the Initiator to edit Employer (Taxabe and Non-Taxable), Employee Share Balances but not EPS Balance"*
  3. `'Transfer of 1.16% Cont From ER Share to EE Share on Account of EPS Contribution on Higher Wages and Adjustment of Amount From EPF Employer Share to EPS Account'`: *"used by the Initiator to move from Employer's to EPS Balance... The amount to be moved to EPS should be equal to or less than Employer's Balance deduction"*
  4. `'Debiting of excess Interest Credited by application software'`: *"used by the Initiator in order deduct any excess interest paid under Employee's Share or Employer's Share"*
* **States / Statuses**:
  * Forwarded by Initiator (green highlight), Submitted, Final recommendations.
* **Key Checks Performed**:
  * Search by UAN/Member ID, select correct Appendix E type, verify OB balance adjustments, ensure diversion to EPS &le; Employer deduction, upload Notesheet with Number and Date, verify generated PDF report.
* **Documents**:
  * Notesheet attachment, Appendix E Report PDF.
* **Rejection / Return Paths**:
  * Verifier/Approver reviews report and provides final recommendations; specific rejection screen "not stated in manual".
* **What Triggers Payment**:
  * Not applicable (internal ledger adjustment, no cash outflow).

### 5.2 How the POC Implements It
* **Status**: Marked as `? | 2 | contribution` in [`docs/endpoint-catalogue.md`](docs/endpoint-catalogue.md#L30) (`POST /office/ledger-adjustments type=APPENDIX_E`), with note: *"Anything with definition_confirmed: false ... stays disabled in the demo UI and shows a 'definition pending' label"*.
* **Code Implementation**: **Not implemented.** No endpoints exist in `services/contribution-service` or `services/claim-service`.

### 5.3 Gaps (Manual vs. POC)
* **HIGH — Appendix E Completely Unbuilt**: While POC documentation flags Appendix E as unconfirmed/disabled, the user manuals define the complete functional specification, including all 4 subtypes, notesheet metadata, and 2-role workflow.
* **HIGH — 1.16% Higher Wages EPS Diversion Missing**: The statutory mechanism to divert 1.16% from employer EPF share to EPS on higher wages is unbuilt.
* **HIGH — Excess Interest Debiting Missing**: No ability for office to recover or debit excess interest credited by software.

### 5.4 Things the POC Does That the Manual Does Not Describe
* None (feature unbuilt).

### 5.5 Concrete, Prioritised Recommendations
1. **[services/contribution-service]**: Implement `POST /api/v1/office/ledger-adjustments` supporting the 4 manual-defined Appendix E adjustment types.
2. **[services/contribution-service]**: Add maker-checker workflow: DA enters adjustment with Notesheet Number, Date, and attachment &rarr; APFC approves.
3. **[apps/web]**: Add `Appendix E` menu under Field Office interface.

---

## 6. Form EDLI 5IF — Insurance Benefit on Death

### 6.1 The Lifecycle in the Manual
* **Roles in Order**: 
  1. Nominee / Claimant (`Form_EDLI_Calim_5IF_User_Manual_-_EDLI_Claims_Module_Member_V1.0.txt`)
  2. INITIATOR (`Form_EDLI_Calim_5IF_User_Manual_-_EDLI_Claims_Module_Initiator_V1.0.txt`)
  3. VERIFIER / APPROVER (`Form_EDLI_Calim_5IF_User_Manual_-_EDLI_Claims_Module_Verifier_Approver__Done.txt`)
* **Screens and Menu Paths**:
  * **Nominee**: Member portal &rarr; `'Death Claim Filing by Nominee (Claims)'` &rarr; enters UAN, Beneficiary Aadhaar, Name, DOB, Mobile, Captcha &rarr; OTP. On dashboard, selects `'Insurance Claim (Form 5IF)'`. Updates Date of Death (if not available). Enters Mobile, Address, Bank details, uploads Death Certificate, DOB Proof, Bank Proof. Aadhaar consent &rarr; OTP &rarr; E-signs form &rarr; View Claim PDF.
  * **INITIATOR**: Top menu `'Claim'` &rarr; Dropdown `'Form 5IF'`. Comprehensive table: `Tracking ID`, `UAN`, `Member ID`, `Member Name`, `Claimant Name`, `Gender`, `Receipt Date and Time`, `Pendency in Days`, `Remarks`, `Filing Mode`, `Filed Through`, `Processing Status`, `Claim Amount(Rs)`, `Count of Previously rejected Claims`, `Reports`. New claims in green. Clicking Tracking ID opens a 3-tab window:
    1. `'Claim Details'`: Reviews auto-populated details, Claim PDF, enclosures (DOB proof, Death certificate, Bank proof), and member ledger.
    2. `'Calculation Details'`: Service Days Calculation; carry-forwarded transactions; Previous Transaction before Date of Death (Month-wise opening balance, EPF wage, month-wise withdrawals). Initiator can click `'Modify Transaction'` link to edit wage/balance rows if needed.
    3. `'Beneficiary Details'`: e-nomination details, bank details. Clicks `'Generate CAD'` button.
    * Decision: `Recommend to Approve` or `Recommend to Reject`. Mandatory remarks, mobile OTP validation.
    * Start-Stop claim: Includes `"Stop Claim Processing"` and `"Restart Claim"`.
  * **VERIFIER / APPROVER**: Top menu `'Claim'` &rarr; Dropdown `'Form 5IF'`. Opens 3-tab window. In Beneficiary Details tab, clicks `'Generate Summary Sheet'`. Decision: `Approve (Recommend to Approve)` or `Send Back to First level (Recommend to Reject)`. **Must e-sign the document** (clicks e-sign option next to View Generated CAD/Summary Sheet button). Mandatory remarks, mobile OTP validation.
* **States / Statuses**:
  * New (green), Pendency in Days, Count of Previously rejected Claims. Actions: `Recommend to Approve`, `Recommend to Reject`, `Approve`, `Send Back to First level`.
* **Key Checks Performed**:
  * Enclosures scrutiny, Service days calculation, month-wise EPF wages for 12 months, carry-forwarded transactions, previous withdrawals, CAD generation, Summary Sheet generation, e-signature by officer, OTP validation.
* **Documents**:
  * Claimant uploads: DOB proof, Death Certificate, Passbook/Cheque. E-signed claim PDF.
  * Office: CAD file, Summary Sheet PDF e-signed by Verifier/Approver.
* **Rejection / Return Paths**:
  * Initiator: `Recommend to Reject`. Verifier/Approver: `Send Back to First level (Recommend to Reject)`.
* **What Triggers Payment**:
  * Manual states: *"Only after OTP validation is the recommendation (approve/reject) successfully recorded, and the claim forwarded to the next level of processing"* (`Form_EDLI_Calim_5IF_User_Manual_-_EDLI_Claims_Module_Verifier_Approver__Done.txt`). Payment execution details are "not stated in manual".

### 6.2 How the POC Implements It
* **Rules & Policy**: Configured in [`config/demo-rules.yaml:death_claims.edli`](config/demo-rules.yaml#L88-L99): `wage_multiplier: 35`, `average_balance_share_bp: 5000`, `balance_bonus_cap_paise: 17500000`, `minimum_paise: 25000000`, `maximum_paise: 70000000`, `minimum_needs_service_months: 12`.
* **Claim Filing**: Handled in [`services/claim-service/app/api/death_routes.py:file_death_claim()`](services/claim-service/app/api/death_routes.py#L59-L121) (`POST /api/v1/claimants/death-claims` with `form_type="FORM_5IF"`). Computes benefit via `edli_benefit()`, sets `fund="EDLI"`, and moves to `UNDER_REVIEW`.
* **Office Decision**: Marked as Planned in [`docs/endpoint-catalogue.md`](docs/endpoint-catalogue.md#L48) (`POST /office/edli-claims/{claimId}/decisions, P | 2 | claim`); processed through generic workflow case in POC.

### 6.3 Gaps (Manual vs. POC)
* **HIGH — 3-Tab Office Calculation UI Missing**: Manual mandates a 3-tab review window (`Claim Details`, `Calculation Details`, `Beneficiary Details`) with month-wise wages/withdrawals and `"Modify Transaction"` capability. POC auto-computes the amount on backend filing using synthetic wage ₹15,000 without a calculation review interface.
* **HIGH — Officer Document E-Signature & Summary Sheet**: Manual requires Verifier/Approver to generate a Summary Sheet and e-sign the document before OTP submission. In POC, officers use standard Keycloak step-up without document e-signing.
* **HIGH — Dedicated Form 5IF Office Queue**: Manual provides dedicated queue with `Pendency in Days`, `Claim Amount`, and `Count of Previously rejected Claims`. POC places EDLI in generic queue.
* **MEDIUM — Start-Stop Claim**: Missing from EDLI Initiator role.

### 6.4 Things the POC Does That the Manual Does Not Describe
* Debits benefit to `AC21_EDLI` reserve rather than member account balance.
* Co-beneficiary addition (`POST .../beneficiaries`) and APFC share reallocation (`PUT .../shares`).

### 6.5 Concrete, Prioritised Recommendations
1. **[services/claim-service, apps/web]**: Implement dedicated 3-tab EDLI review screen with month-wise wage verification.
2. **[services/claim-service/death_routes.py]**: Add Summary Sheet generation and officer e-sign step.
3. **[services/claim-service/routes.py]**: Add "Start-Stop Claim" support to EDLI claims.

---

## 7. Physical Claim — PRO Counter Intake & Processing

### 7.1 The Lifecycle in the Manual
* **Roles in Order**: 
  1. Member / Beneficiary / Survivor (presents physical form at counter)
  2. PRO / Help Desk Official / Initiator (`Physical_claim_User_Manual_-_Physical_File_Claim_v2.txt`)
  3. Downstream field office adjudication desks
* **Screens and Menu Paths**:
  * **Counter Official**: Login (User ID, Password, Captcha, 2FA OTP) &rarr; Homepage &rarr; Member section &rarr; Click `'Physical Claim Receipt'` link.
  * **Member Search**: Enters any one of `'UAN / Member ID / PPO No'` &rarr; Clicks `'Get Details'`. Selects Member ID from `'Request received against Member ID'`. Can click `'View Member History'` (pop-up) or `'View Member Ledger'` (PDF in new tab).
  * **Header Fields**: Enters `Email ID` and mandatory `Mobile No.`. Selects `Claim mode`, selects `Form Type` (`Single` or `CCF`), selects `Filed By` (`Member` or `Beneficiary/Survivor`; if Beneficiary/Survivor, system asks for Date of Death if not present).
  * **Permissible Request Form Types**:
    1. `PF Final Settlement (Form-19)`
    2. `Withdrawal Benefit (Form-10C)`
    3. `Transfer Claim (Form-13)`
    4. `PF Advance Claim (Form-31)` (requires Para Type, Amount &ge; ₹1,000 and &le; eligible)
    5. `Scheme Certificate Surrender`
    6. `Form – 10D (Pension)`
    7. `PPO Amendment`
    8. `Death Updation`
    9. `Physical LC Updation`
    10. `Spouse Remarriage Updation`
  * **Enclosures & Submission**: Displays form-specific mandatory enclosures based on Para Type. User uploads PDF in `'Additional Supporting Document'`. Checks consent statement &rarr; clicks `'Submit'` &rarr; confirmation pop-up (`'Yes'`).
  * **Receipt**: Screen displays Claim Number and tracking details. Clicking `"click here"` opens the Claim Receipt in a pop-up window for printing and handover to the applicant.
* **States / Statuses**:
  * Physical Claim Receipt generated, Claim Number issued, Tracking Details active.
* **Key Checks Performed**:
  * Counter document verification, UAN/Member ID/PPO search, member ledger verification, mandatory mobile number, para type selection, claim amount check (&ge; 1000 and &le; eligible), PDF document upload, consent check.
* **Documents**:
  * Physical form, supporting documents uploaded as PDF (`Additional Supporting Document`), printed Claim Receipt.
* **Rejection / Return Paths**:
  * Counter official rejects deficient paper applications at the desk before submission.
* **What Triggers Payment**:
  * Generates claim number and routes into backend adjudication. Payment triggered downstream upon approval.

### 7.2 How the POC Implements It
* **Intake Endpoint**: Handled in [`services/claim-service/app/api/death_routes.py:inward()`](services/claim-service/app/api/death_routes.py#L226-L247) (`POST /api/v1/office/physical-claims`) by `fo.pro_intake` or `fo.diary`. Accepts `IntakeInput(form_type, uan, ppo_id, filed_by, claim_mode, details)`. Supports 13 form types in `PRO_FORMS`.
* **Routing**: Pension updations are set to `ROUTED` and forwarded to the pension updation tracker via `PhysicalClaimInwarded.v1`. Claim forms are set to `INWARDED`.
* **Identity Validation**: Handled in [`services/member-service`](docs/endpoint-catalogue.md#L46) (`POST /office/physical-claims/{intakeId}/identity-validations`).
* **Navigation**: Menu item `PRO counter: physical claims` (`/office/pro-counter`) in [`apps/web/src/data/navigation.ts:fieldOffice()`](apps/web/src/data/navigation.ts#L61).

### 7.3 Gaps (Manual vs. POC)
* **HIGH — Inwarding vs. Complete Claim Entry**: In the manual, the counter user enters full claim parameters (Para Type, amount, bank details, PDF upload) and generates a formal Claim Number (`CLM-...`) with receipt. In the POC, `POST /office/physical-claims` only creates a diary intake record (`INW-...`) that stops at `INWARDED` without downstream conversion into an actionable claim case.
* **HIGH — Composite Claim Form (CCF) Mode**: Manual explicitly supports `Form Type: Single` or `Form Type: CCF`. POC marks CCF as Planned (phase 3) and lacks composite intake.
* **MEDIUM — Document PDF Attachment**: Manual includes an `'Additional Supporting Document'` PDF upload field. POC `IntakeInput` accepts a JSON `details` map without PDF multipart upload.
* **MEDIUM — Printable Claim Receipt Pop-up**: Manual features a pop-up claim receipt with tracking details. POC returns a raw JSON envelope.
* **LOW — Direct PPO No / Member ID Lookup**: POC requires `uan` in `IntakeInput`; manual allows searching by UAN, Member ID, or PPO No.

### 7.4 Things the POC Does That the Manual Does Not Describe
* Dedicated Identity Validation step (`POST .../identity-validations`) verifying applicant against member registry before allowing DA entry.
* Automated event-driven routing of pension updations directly into `pension-service` updation tracker.

### 7.5 Concrete, Prioritised Recommendations
1. **[services/claim-service/death_routes.py]**: Add endpoint to transition `INWARDED` physical claims into active adjudication cases (`CLM-...`) in `cases` table.
2. **[services/claim-service/death_routes.py]**: Add multipart PDF upload support to physical intake.
3. **[apps/web/src/routes/office/pro-counter]**: Implement printable receipt modal with tracking barcode/number.

---

## 8. Summary Comparison Table

The following table summarizes all 7 areas across key dimensions, comparing the manual against the POC implementation:

| Module / Form | Manual Lifecycle & Roles | POC Implementation | Key Gaps | Gap Severity | Priority File to Change |
|---|---|---|---|---|---|
| **Form 19** (Final Settlement) | Member &rarr; Initiator &rarr; Verifier 1 &rarr; Verifier 2 &rarr; Approver. CAD generated at each step. Start-Stop claim. | Member &rarr; DA &rarr; SS/AO &rarr; APFC/OIC &rarr; Cashier. CAD generated post-approval by F&A wing. Auto-settlement &le; ₹1L. | CAD timing inverted (post-approval vs. during scrutiny); 3-tier verifiers flattened to 2; no Start-Stop claim. | **HIGH** | [`services/claim-service/app/api/lifecycle_routes.py`](services/claim-service/app/api/lifecycle_routes.py) |
| **Form 20** (Death Claim) | Beneficiary &rarr; Initiator &rarr; Verifier &rarr; Approver. Beneficiary logs in with UAN + Aadhaar; uploads enclosures; e-signs. | Generic `claimant` persona; APFC share reallocation; cashier pays after 100% shares. | No beneficiary self-service portal login; no enclosure upload at filing; Date of Death must be pre-recorded by employer. | **HIGH** | [`services/claim-service/app/api/death_routes.py`](services/claim-service/app/api/death_routes.py) |
| **Form 31** (PF Advance) | Member &rarr; Initiator &rarr; Verifier 1 &rarr; Verifier 2 &rarr; Verifier 3 &rarr; Approver. Rejection loops back to Initiator. White/red purpose UI. | Member &rarr; DA &rarr; SS/AO &rarr; APFC/OIC &rarr; Cashier. Direct final rejection. Only `ADVANCE_ILLNESS` baseline. | Rejection workflow violates manual (immediate termination vs. return to Initiator); Verifier 3 tier missing; CAD during scrutiny missing. | **HIGH** | [`services/workflow-service/app/api/routes.py`](services/workflow-service/app/api/routes.py) |
| **Form 10C** (Withdrawal / Certificate) | Member &rarr; Initiator &rarr; Verifier/Approver. Return to DA for wage correction. NCP days deduction. | Cash benefit unbuilt (P). Scheme Certificate auto-issued immediately without officer review. | Form 10C cash withdrawal unbuilt; Scheme Certificate bypasses office adjudication; no return for wage correction. | **HIGH** | [`config/demo-rules.yaml`](config/demo-rules.yaml) & [`services/pension-service/app/api/settlement_routes.py`](services/pension-service/app/api/settlement_routes.py) |
| **Appendix E** (Ledger Adjustments) | Initiator &rarr; Verifier/Approver. 4 adjustment types (Other, Interest Return, 1.16% EPS diversion, Excess interest debit). Notesheet. | Flagged as unconfirmed (`?`) and disabled in POC. | Entirely unbuilt despite complete functional manual specification; 1.16% higher wages diversion missing. | **HIGH** | [`services/contribution-service`](services/contribution-service) |
| **EDLI 5IF** (Insurance Claim) | Nominee &rarr; Initiator &rarr; Verifier/Approver. 3-tab review (Details, Calculation, Beneficiary). Summary Sheet. Officer e-sign. | Backend benefit calculation on filing; generic workflow review; debits EDLI fund. | No 3-tab calculation UI; no Summary Sheet generation; no officer document e-sign; generic work queue. | **HIGH** | [`services/claim-service/app/api/death_routes.py`](services/claim-service/app/api/death_routes.py) |
| **Physical Claim** (PRO Counter) | PRO counter official completes full claim data entry (Para Type, amount, enclosures, PDF upload) and issues receipt. | Counter creates diary intake record (`INW-...`) and validates identity. | Inwarding only (does not convert into active claim cases for DA review); CCF mode missing; no receipt modal. | **HIGH** | [`services/claim-service/app/api/death_routes.py`](services/claim-service/app/api/death_routes.py) |

---

### Key Takeaway for Government Demo
The POC excels in architectural integrity, event-driven ledger consistency, cryptographic audit trails, policy administration, and automated test coverage. However, for an official EPFO government demonstration, the **greatest points of friction** against the user manuals are:
1. **The Inversion of CAD**: In the manuals, CAD is an operational docket required *before* approval; in the POC, it is an authorization document created *after* approval by an unrelated desk (`fo.fa_accounts`).
2. **Rejection Semantics**: In the manuals, intermediate verifiers cannot reject a claim; they must return it to the Initiator to re-forward upward as "Recommend to Reject". In the POC, any officer can reject immediately.
3. **Missing Form 10C Cash & Appendix E**: Both are fully detailed in EPFO manuals but remain unbuilt or unadjudicated in the POC.
4. **Beneficiary Intake Model**: Form 20 and Form 5IF manuals detail a direct UAN + Aadhaar OTP beneficiary portal with document uploads, whereas the POC currently uses a pre-seeded claimant persona with paper-counter intake.
