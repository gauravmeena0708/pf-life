# EPFO Portal Functions by Login Type

> Research input for `docs/endpoint-catalogue.md`. It records what each real EPFO login lets a user do, so the API list can be checked against it before it is finalised.
>
> **Evidence levels.** **V** = exact label seen in an official EPFO manual, booklet or screenshot (source given). **D** = the function is documented officially but its exact menu label is not confirmed. Only public manuals were used; nobody logged in to a live portal. Portal labels change over time, so older manuals are flagged.
>
> Researched 2026-09-26 by Claude, with Codex and AGY. AGY's employer menu tree was **not used**: 5 of its cited source PDFs were checked in the Wayback Machine and never existed, and it gave VDR an invented expansion ("Verification Data Record").

**Sources**

| Key | Document |
|---|---|
| [EB] | EPFO, *Information Booklet for the employers of newly covered establishments* — `epfindia.gov.in/site_docs/PDFs/MiscPDFs/Employer_Information_Booklet.pdf` (archived copy read in full) |
| [UM] | EPFO IS Division, *User Manual: UAN & KYC functions in OTCP* v1.4 — `…/UAN_PDFs/UAN_ForEmployers/UserManual_Ver1.4_Employers_new.pdf` (**older portal**; archived copy read in full) |
| [ECR] | EPFO, *User Manual: Re-engineered ECR* v3.0 — `…/MiscPDFs/User-Manual-ReECR_v3.0.pdf` (read by Codex) |
| [UAN2] | EPFO, *UAN 2.0 employer workflow manual* — `…/EPFOUnifiedPortal/UserManual_UAN2.0.pdf` (read by Codex) |
| [EXR] | EPFO, *Exempted Establishment Return manual* and FAQ (read by Codex) |
| [IWU] | EPFO circular, *International Workers online CoC system* — `…/Circulars/Y2017-2018/IWU_OnlineSystem_COC_10677.pdf` (read by Codex) |
| [GMS] | EPFO, *EPFiGMS user manual / SOP* (older; read by Codex) |
| [PP] | Pensioners' Portal public enquiry pages — `mis.epfindia.gov.in/PensionPaymentEnquiry/…` (read by Codex) |
| [JD] | EPFO SOP on Joint Declaration, 2024 (member-portal screenshots; read by Codex) |

---

## 1. Employer login — Unified Portal for Employers

**Top-level menus seen in screenshots [ECR][UAN2]:** Home · Establishment · Member · Payments · Online Services · Dashboards · User · Admin · ABRY · Past Accum. · File Upload · Surrender Exemption. The last four only appear for some establishments (incentive-scheme or exempted).

| Menu path | What it does | Ev. | Source | Catalogue |
|---|---|---|---|---|
| **Home** → Alerts | Pending items: KYC awaiting approval, member basic-detail approve/reject, KYC seeded at registration | V | [EB] | ➕ missing |
| **Establishment** → Form 5A | Ownership / branches / bank / contact return, signed with DSC or e-sign; update whenever these change | V | [EB] | §2 ✔ |
| Establishment → Branches (Form 2A) | Branch / division details to obtain a sub-code | V | [EB] | §2 ✔ (as "branches") |
| Establishment → DSC/e-sign → Digital Signature Registration | Register a USB-token DSC; generate request letter for the PF office; revoke option | V | [EB] | §3 ✔ |
| Establishment → DSC/e-sign → e-sign Registration | Register Aadhaar e-sign (DSC holder or non-DSC holder with VID) | V | [EB] | §3 ✔ |
| **Member** → Register-Individual | Create a UAN for a new joinee, or link an existing UAN ("Previous Employment/UAN = YES"); Form 11 retained by the employer | V | [EB], [UAN2] | §4 ✔ |
| Member → Register-Bulk | Bulk registration by file | V | [EB], [UAN2] | §4 ✔ |
| Member → Member Profile | Search a UAN; view the profile; add KYC; mark date of exit | V | [EB], [UAN2] | ➕ profile view missing |
| Member → Approvals | Approve marked exits and other member changes | V | [EB], [UAN2] | ➕ generic approvals missing |
| Member → Approve KYC pending for Digital Signature | Approve Aadhaar KYC after UAN creation, with DSC / e-sign | V | [EB] | §4 ✔ |
| Member → Approve KYC seeded by member | Approve KYC the member added themselves | V | [EB], | §4 ✔ |
| Member → KYC BULK | Link KYC to UANs in bulk | V | [EB], [UAN2] | ➕ missing |
| Member → Exit-Bulk | Mark exits in bulk | V | [EB], [UAN2] | ➕ missing (single exit only) |
| Member → Missing details | Fill in incomplete member profile fields | V | [EB] | ➕ missing |
| Member → Member Location Mapping | Map employees to branch locations | V | [EB] | ➕ missing |
| Member → KYC Verification / PAN Verification | Verify KYC / PAN | V | [UAN2] | ➕ missing |
| Member → Joint Declaration requests | Attest member profile corrections | D | [JD] | §4 ✔ |
| **Payments** → ECR Upload (ECR Help File) | Upload the monthly ECR text file | V | [EB] | §5 ✔ |
| Payments → Return Filing (Quick Links) → Return home page | File a return, view / pay challan, file arrear return, filing history | V | [ECR] | §5 ✔ |
| Payments → Return monthly dashboard | Wage-month summary; view / upload return | V | [ECR] | ➕ missing |
| Payments → Regular / Supplementary / Revised return | Return variants | D | [ECR] | §5 ✔ (revised = supplementary?) |
| Payments → ECR/Return Filing → **Direct Challan** → Challan Entry → *Miscellaneous charges challan* | Employer-created challan for **14B penal damages** and **7Q interest** ("Miscellaneous") | V | [EB] | ⚠ catalogue models these as office-raised "demands"; must allow an employer-initiated direct challan |
| Payments → … → Direct Challan → Challan Entry → *Administrative/inspection charges challan* | Admin charges only (e.g. keeping a code alive with no members) | V | [EB] | ⚠ same as above |
| Payments → ECR/Return filing → Monthly Return for Exempted Establishment | Exempted return, Parts A–F (establishment, trust, employment, contribution, investment, annual) | V | [EXR] | §11 ✔ (parts not modelled) |
| Payments → TRRN query / challan status / receipt | Check status of a TRRN and its payment | D | [ECR] | §5 ✔ |
| **Online Services** → Transfer Claims | Pending member transfer claims to forward to the field office | V | [EB] | §4 ✔ |
| Online Services → claim attestation, higher-pension joint-option validation | Attest claims; validate joint options | D | EPFO higher-pension circulars | §4 ✔ |
| **Dashboards** → Active Members details | Download live members with UAN and KYC as Excel | V | [EB] | ➕ missing |
| Dashboards → Missing details | Members with incomplete profiles | V | [EB] | ➕ missing |
| **User** / **Admin** | Menus seen; contents not documented (likely sub-user / operator management and password) | D | [ECR][UAN2] | §3 operators ≈ |
| **ABRY** | Aatmanirbhar Bharat Rozgar Yojana incentive-scheme functions (a past scheme; newer incentive schemes may replace it) | D | [ECR] | ➕ missing (incentive schemes) |
| **Past Accum.** | Exempted establishments: transfer of past accumulations | D | [ECR] | §11 ✔ |
| **File Upload** | Generic document upload | D | [ECR] | ➕ missing |
| **Surrender Exemption** | Surrender a Section 17 exemption | D | [ECR] | §11 ✔ |
| UAN → Search UAN ID (own / other establishment) · Confirm Previous Employment · Download UAN List · History PDFs | UAN lookup and previous-employment confirmation (**older OTCP portal**; probably folded into Member menus now) | V (old) | [UM] | ➕ missing |
| KYC → Upload Bulk KYC Text File · Approve Bulk KYC PDF · View Approved KYC · Update Incomplete Members Details · Error List | Bulk KYC workflow (**older OTCP portal**) | V (old) | [UM] | ➕ partly missing |
| Digital Certificate → Register Certificate · View/Revoke Certificate | DSC register / revoke (**older OTCP portal**) | V (old) | [UM] | §3 ✔ |
| Closure / deregistration | Apply to deregister the code, with supporting documents | D | [EB] | §2 ✔ |
| Principal employer: contractors, work orders, contract-worker details | Record contractors, contracts, workers | D | EPFO Principal Employer page | §2 ✔ |

## 2. Member login — Unified Member Portal and Passbook

| Menu path | What it does | Ev. | Source | Catalogue |
|---|---|---|---|---|
| Home | Landing page | V | [JD] | — |
| View → (profile, service history, UAN card, passbook) | Read-only member information | V (menu) / D (items) | [JD] | §6 ✔ |
| Manage → Modify Basic Details | Profile correction (Joint Declaration) | V | [EB], [JD] | §6 ✔ |
| Manage → KYC → Add KYC | Seed Aadhaar / bank / PAN | V | [EB] | §6 ✔ |
| Manage → Contact Details | Change mobile / email | V | [JD] | §6 ✔ |
| Manage → E-Nomination, Mark Exit | Form 2 nomination; self-marked exit | D | EPFO circulars | §6 ✔ |
| Online Services → Claim (Form-31, 19, 10C & 10D), transfer (Form 13), track claim, joint declaration, higher-pension application status | Claims and transfers | D | [JD], EPFO FAQs | §7 ✔ |
| Important Links → Activate UAN | UAN activation | V | [EB] | §6 ✔ |
| Passbook site | Passbook and claim status (separate login) | V (login page) | passbook.epfindia.gov.in | §6 ✔ |

## 3. Pensioner — Pensioners' Portal (public enquiries, no dashboard login found)

| Label | What it does | Ev. | Source | Catalogue |
|---|---|---|---|---|
| Jeevan Pramaan Enquiry | Life-certificate status by Jeevan Pramaan transaction ID | V | [PP] | §1 ✔ |
| Know your PPO No. | Find PPO number | V | [PP] | §1 ✔ |
| PPO Enquiry / Payment Enquiry | Pension payment details | V | [PP] | §1 ✔ |
| Know Your Pension Status | Status by office + PPO | V | [PP] | §1 ✔ |
| Know Your Pension Payee Bank | Which bank pays the pension | V | [PP] | ➕ missing |
| Bank Acc. No. Search / Mem. ID Search | Search keys used by the enquiries above | V | [PP] | §1 ✔ |

## 4. Exempted establishment (PF trust)

No separate trust login found; the employer files through the ECR menu [EXR]. See the employer rows Monthly Return for Exempted Establishment, Past Accum. and Surrender Exemption.

## 5. International Workers portal

| Label | What it does | Ev. | Source | Catalogue |
|---|---|---|---|---|
| Login roles: EMPLOYER · EPFO · FOREIGN AGENCIES | Three separate login types | V | [IWU] | ➕ foreign-agency role missing |
| APPLICATION FOR COC | Apply for Certificate of Coverage | V | [IWU] | §12 ✔ |
| APPLICATION FOR EXTENSION OF COC | Extend a CoC | V | [IWU] | §12 ✔ |
| UPLOAD SIGNED APPLICATION FOR COC | Upload the signed application | V | [IWU] | ➕ missing |
| DOWNLOAD CERTIFICATE OF COVERAGE | Download the issued CoC | V | [IWU] | ➕ missing |

## 6. EPFiGMS (grievances)

| Side | Labels | Ev. | Source | Catalogue |
|---|---|---|---|---|
| Complainant | Register Grievance (as PF member, EPS pensioner, employer, others); reminder; view status | V / D | epfigms.gov.in, [GMS] | §1, §13 ✔ |
| Officer | NEW GRIEVANCE · PARENT OFFICE · DIRECTLY RECEIVED FROM CITIZEN · PARTLY TRANSFERRED/TRANSFERRED CASES · CASE REPORTS/REPLIES · DISPOSALS · REMINDER/CLARIFICATION · CASES ESCALATED · CORRESPONDENCE LETTERS · REPORTS · LODGE LOCAL GRIEVANCE · CREATE WINGS/GROUP | V (**older manual**) | [GMS] | ➕ transfers between offices, officer-lodged grievance, correspondence letters, wings/groups, reports missing |

## 7. UMANG (EPFO services)

Service groups from EPFO's published listing, not a current in-app screenshot:
- **Employee centric:** View Member Passbook, Raise Claim, Track Claim.
- **Employer centric:** Get Remittance Details by Establishment ID, Get TRRN Status.
- **General:** Search Establishment, Search EPFO office, Know your claim status, account details by SMS / missed call.
- **Pension:** Jeevan Pramaan, View passbook (Pension).

All already in the catalogue (`init.md` interface 20 simulates UMANG over the same APIs), except SMS / missed-call balance, which is out of scope.

## 8. Field office (staff) logins

Field-office staff do not use a public portal. They work in the **FO Application Software / "FO Interface"**, with **e-Office** for files, a **Diary / Inter-Section Diary** module for physical papers, an ISD **Issue Tracker**, and (at national level) **CPPS**, the Centralised Pension Payment System run by a Central Payment and Reconciliation Centre at NDC Dwarka [PM]. No full menu tree is published. The roles, functions and approval chains below come from three official EPFO documents, and exact menu paths are quoted where the documents give them.

**Additional sources**

| Key | Document |
|---|---|
| [PM] | EPFO, *Pension Manual — Manual of Accounting Procedure, EPS 1995* (`…/Downloads_PDFs/Pension_Manual.pdf`, archived Aug 2025; read in full) |
| [FIA] | EPFO SOP FIA/2023/1, *Freezing/de-freezing of MID/UAN/Establishment*, 22/12/2023 (`…/Circulars/Y2024-2025/Circular_FIA_04072024.pdf`, archived; read in full) |
| [WSU] | EPFO SOP 01/2024 v2, *Transaction-less and Inoperative accounts in EPFO*, 02/08/2024 (`…/Circulars/Y2024-2025/Circular_SOP_WSU_02082024.pdf`, archived; read in full) |
| [FRM] | EPFO, *Success stories* — RO Bengaluru Central, *Fraud risk mitigation* (`…/Updates/Success_Story_EPFO.pdf`, archived) |
| [EP] | Compliance e-Proceedings portal, public menu labels (opened by Codex) |

### 8.1 Roles and what each one does

| Role | Functions (menu path where documented) | Ev. | Source |
|---|---|---|---|
| **DA (Accounts)** — dealing assistant, accounts group | Process claims: online Form 10C/10D claims land in the workload at **Claims > Transaction > Form-10D/10C**; withdrawal benefit at **Claim > Transactions > Form-10C – Scheme Certificate/W Benefit** · Prepare the **Input Data Sheet (IDS)** for pension/scheme-certificate cases · Update service history, date of joining/exit, reason for exit in the FO Interface before an early-pension claim · Maintain member records (Form 9, contributions, e-nomination) · Verify pension-fund remittances from the member ledger · Process inoperative-account claims and KYC-update requests that land in the DA's login · Open e-files for freeze / de-freeze verification · Start "crowdsourcing" verification of a member through co-workers' logins · Enter **Member VDR** deposits (drop-down purpose, e.g. "Pension on Higher Wages", Application ID mandatory) · Use **Appendix-E** with a special code to move PF employer share (A/c 01) to the pension fund (A/c 10) | V (paths) / D | [PM] [WSU] [FIA] |
| **SSA / DA (claims)** | First level of every claim-settlement chain (see 8.2) | D | [FIA] [WSU] |
| **SS / AO (Accounts)** — section supervisor / accounts officer | Review the DA's work; approve IDS (claims move "to login of Accounts Officer for approval"); second or third level of claim and inoperative-account chains; review freeze / de-freeze verification | D | [PM] [FIA] [WSU] |
| **DA (Compliance)** | Open and complete e-file verification of a frozen **establishment** | D | [FIA] |
| **SS (Compliance)** | Review DA (Compliance) verification; pass to the Circle Officer (APFC/RPFC-II) | D | [FIA] |
| **APFC / RPFC-II** (accounts or circle officer) | Approve higher-value claims · Order freezing of a MID/UAN (category B/C) · Verify freeze cases and pass to OIC · Approve exceptional Appendix-E / VDR (Special) credits (RPFC-II F&A only) | D | [FIA] [FRM] |
| **OIC** — officer in charge of the office | Order freezing of an establishment (category B) · Final office-level validation and recommendation to de-freeze · Approve claims over the top threshold · Report suspected fraud to ISD and the regional fraud-risk committee · Monitor unblocking requests daily | D | [FIA] [WSU] |
| **DA (Pension)** | **Pension > Transaction > Pension Worksheet** (worksheet from the IDS) · Generate PPO · Initial arrear · Dispatch and scroll after e-sign · **Pension > Transaction > Transfer in with PPO / Transfer in without PPO** · **Special 10D module** for cases with incomplete service/wage data · Send data errors back to Accounts through a "need to edit" option | V (paths) / D | [PM] |
| **SS (Pension)** | Approve transfer-in entries (with AO(P)); pass initial arrears to APFC(Pension) | D | [PM] |
| **APFC / AC (Pension)** — in charge of the RO pension wing | Approve worksheet and PPO · **E-sign the PPO** · Authorised Officer for PPO issue · Scheme certificates · PPO transfer in / out · Release PPOs to the link bank daily, reconcile bank paid statements, bank service charges · Pensioner master-file changes, non-drawal checks · **Monitor Digital Life Certificates (DLC)**, due-basis claims, death / accidental-death claims · Family Pension 1971 (Form 10A) PPOs | D | [PM] |
| **Pension Disbursement Section** | Bank agreements; forward approved PPOs to the bank; monthly list of pensioners; NEFT of monthly pension to the link branch; PPO-wise / branch-wise lists; credit on the last working day | D | [PM] |
| **Cash Branch** | Pay approved withdrawal benefits; handle cheques deposited through VDR; one of the sections in the VDR-ECR correction process | D | [PM] [FRM] |
| **Enforcement Officer** | Verify and certify an employer's revised ECR for major corrections (VDR-ECR process) | D | [FRM] |
| **Diary section** | Diarise physical claims and documents in the diary module; inter-section diary between Accounts and Pension | D | [PM] |
| **Compliance officers (APFC/RPFC as quasi-judicial authority)** | e-Proceedings: Case Status, Daily Order, Final Order, Cause List; MIS reports (office / period / zone wise, filing, pending, disposal, virtual hearing); HO reports for 7A and 14B & 7Q | V (labels) / U (role) | [EP] |
| **ISD (IS Division, NDC)** | Issue Tracker with a "freezing/de-freezing request" category; block / unblock accounts on the authorised officer's order; pop-up messages on member / employer logins | D | [FIA] |
| **Zonal / Head Office** (RPFC-I at ZO, FIA vertical, Pension verticals) | Order freezing (category A–C at HO/ZO level); fraud-risk monitoring; pension policy, DLC / higher-pension monitoring; CPPS operations | D | [FIA] [PM] |

### 8.2 Approval chains (maker → checkers)

These chains are real EPFO delegation rules. The POC must load them from `config/demo-rules.yaml` as **illustrative, editable** thresholds, never hard-code them (`init.md` §0.5).

| Process | Chain | Source |
|---|---|---|
| Claim settlement, normal | ≤ ₹50,000: SSA → SS · ₹50,000–5 lakh: SSA → AO · ₹5–25 lakh: SSA → SS → APFC/RPFC-II · > ₹25 lakh: SSA → AO → OIC | [FIA] 8(xvi), [WSU] 5.4.2 |
| Claim settlement after de-freezing | ≤ ₹50,000: SSA → SS → AO · ₹50,000–5 lakh: SSA → AO → APFC/RPFC-II · ₹5–25 lakh and > ₹25 lakh: SSA → AO → APFC/RPFC-II → OIC (ZO informed; concurrent audit) | [FIA] 8(xvi) |
| Inoperative-account settlement | Several amount bands (up to ₹5 lakh / ₹5–25 lakh / above ₹25 lakh), each starting DA (Accounts) → SS / AO → APFC/RPFC-II or OIC | [WSU] 5.1, 5.5 |
| Freeze verification — member (MID/UAN) | DA (Accounts) → SS/AO (Accounts) → APFC/RPFC-II → OIC → authorised officer, with a day-by-day timeline | [FIA] 8 |
| Freeze verification — establishment | DA (Compliance) → SS (Compliance) → APFC/RPFC-II (Circle Officer) → OIC → authorised officer | [FIA] 8 |
| Pension (PPO) | Accounts: DA (Accounts) → AO approves IDS → Pension: DA(Pension) worksheet → APFC(Pension) · PPO → APFC(Pension) · initial arrear → SS(P) → AC(P) · e-sign by AC(P) → DA(Pension) dispatch | [PM] 11.7, 11.9 |
| Appendix-E / VDR (Special) credit to a member | Exceptional only; RPFC-II (F&A) approval (per RO Bengaluru Central practice; a DA at FO level may only debit) | [FRM] |

### 8.3 What "freezing" blocks

A frozen MID/UAN/establishment cannot log in, generate or link a UAN, change profile / KYC / DSC, receive Appendix-E / VDR Special / VDR Transfer-in deposits, settle claims or transfers, or register a new establishment on the same PAN/GSTN/Aadhaar/DSC [FIA] 4.7.


---

## Gaps this adds to the API list

The employer login is where most of the missing functions are:
1. **Direct Challan** created by the employer (14B / 7Q "miscellaneous" and admin/inspection charges), alongside office-raised demands.
2. **Home alerts** and **Dashboards** (active-members download, missing details).
3. **Member Profile** view, the generic **Approvals** queue, **Missing details** update.
4. **Bulk** KYC and **bulk** exit.
5. **Member Location Mapping**, **KYC / PAN verification**.
6. **UAN search / confirm previous employment / download UAN list**.
7. **Return monthly dashboard**; whether **Revised** return is distinct from Supplementary.
8. **Incentive schemes** (ABRY and successors) and a generic **File Upload**.
9. **User / Admin** menus — confirm they are sub-user management (our operators).

Field office: role-based queues (DA / SS / AO / APFC / OIC and pension-section roles) with **amount-based approval chains** loaded from config; IDS → worksheet → PPO → e-sign pipeline; Member VDR and VDR-ECR correction flow; freeze / de-freeze with the blocked operations above; diary / e-file references; Issue Tracker requests.

Other logins: International Workers **foreign-agency** role, CoC signed-upload and download; EPFiGMS **officer** functions (inter-office transfer, local lodging, letters, reports); pension **payee-bank** enquiry.
