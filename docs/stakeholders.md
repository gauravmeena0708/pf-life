# Stakeholder Register

> The first step towards a per-stakeholder API set. It lists **every party that acts on, approves, oversees, supplies data to, or consumes data from** the EPFO platform, including offices and roles that have no dedicated system role today but will need one in the future system.
>
> Next steps: `docs/stakeholder-activities.yaml` (activities and hand-offs per stakeholder), then an API set per stakeholder generated from it.

## How to read this

| Column | Meaning |
|---|---|
| **ID** | Stable key used in the activity map, permission matrix and Keycloak roles |
| **Today** | How this stakeholder uses EPFO systems now, as far as public sources show. **Login** = has its own login/screens · **Via** = works through another party's system (e-Office file, email, paper) · **None** = no system role found |
| **Future** | **Core** = must be modelled in the new system · **New** = new role or a role that exists on paper but needs system access · **Ext** = external system, integrated through an adapter · **Read** = read-only / aggregate consumer |
| **POC** | Seeded persona in `init.md` §6.2 (✔), or a persona to add (➕) |
| **Src** | Evidence: MAP = Manual of Accounting Procedure Part I · AUD = Audit Manual · CMP = Compliance Manual · REC = Recovery Manual · EXM = Exemption Manual · PEN = Pension Manual · EDLI = EDLI Manual · ICF = Manual for Inspector-cum-Facilitator · SOP-B = Part B SOPs & Service Standards · EC = 98th Executive Committee agenda · FIA / WSU / JD = SOPs on freezing, inoperative accounts and Joint Declaration · OUL = EPFO "Logins for Office Use" page · REF = PIB "EPFO Reforms", 12 Feb 2026 · FRM = RO Bengaluru fraud-risk note · IWU = IWU CoC circular · SS = Samadhan Setu issue tracker · WEB = other public source |

All sources are official EPFO documents downloaded in September 2026 (list at the end). Mentions were counted across roughly 80,000 lines of manual text; any stakeholder with no documentary hit is marked as such.

---

## A. Members, beneficiaries and the public

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `public` | Public visitor (establishment search, calculators, circulars) | Login-free pages | Core | ✔ | WEB |
| `member` | Member — active contributor (UAN holder) | Login (Member portal, UMANG) | Core | ✔ (A, B) | MAP, WSU |
| `member.exited` | Member — exited / inoperative account holder | Login + FO visit / NAN camp | Core | ➕ | WSU |
| `member.disabled` | Member with disability (disablement pension) | Via FO | Core | — | PEN |
| `pensioner` | Pensioner (member / early / disablement pension) | Public enquiries, UMANG, Jeevan Pramaan | Core | ➕ | PEN |
| `family_pensioner` | Widow(er), child, orphan, dependent-parent pensioner | Via FO, Jeevan Pramaan | Core | ➕ | PEN |
| `claimant` | Nominee / legal heir / guardian claiming PF, EDLI or pension on death | Via FO (paper) + online death claims | Core | ➕ | PEN, EDLI |
| `claimant.nominee` | Co-beneficiary on a multi-beneficiary death claim (PF / EDLI / pension) holding an allocated percentage share, including shares already settled in the legacy system | Via FO / online death claims | Core | ➕ | EDLI, PEN, SS |
| `intl_worker` | International worker (inbound or outbound, CoC holder) — since P2.9a a member attribute (`members.international`), signs in with the `member` role | Login (IWU portal via employer) | Core | ➕ | MAP, EC |
| `complainant` | Grievance complainant who is not logged in (member, pensioner, employer, other) | Login-free (EPFiGMS) | Core | ➕ | WEB |
| `rti_applicant` | RTI applicant | Via RTI portal / paper | Read | — | PEN, EC |

## B. Employers and intermediaries

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `employer.owner` | Establishment owner / employer (legal entity) | Login (Employer portal) | Core | ✔ | MAP, CMP |
| `employer.signatory` | Authorised signatory (registered DSC / e-sign) | Login | Core | ✔ | MAP, JD |
| `employer.operator` | Employer sub-user / payroll preparer | Login (User / Admin menus) | Core | ✔ | WEB |
| `principal_employer` | Principal employer monitoring contractors | Login | Core | ➕ | CMP, SOP-B |
| `contractor` | Contractor establishment (tags its workers to a principal employer) — since P2.12b its own employer users (`employer.operator`) do this | Login | Core | ➕ | CMP |
| `exempted.trust` | Exempted establishment — PF trust and its Board of Trustees | Login (employer ECR menu) | Core | ➕ | EXM (219 mentions of trustees) |
| `trust_auditor` | Chartered accountant auditing an exempted trust | Via trust | New | — | EXM |
| `payroll_provider` | Payroll software / HRMS vendor acting for employers | None (portal file uploads) | New (B2B API) | ✔ | — (`init.md` interface 13) |
| `csc_operator` | Common Service Centre / assisted-access operator (e.g. DLC, UAN) | Via CSC systems | New | — | PEN, EC |
| `liquidator` | Official liquidator / resolution professional of a closed or insolvent employer | Via FO correspondence | New | — | SOP-B, CMP (116 mentions) |
| `exempted.trust_liquidator` | Exemption surrender officer / liquidator of a PF trust — hands over past accumulations and member ledgers when an exemption is surrendered or cancelled | Via trust / FO correspondence | Core | ➕ | EXM, SS |

## C. Field office — Regional Office (RO) and Sub-Regional Office

EPFO field offices run branches (Accounts, Pension, Cash, Compliance, Recovery, Legal, Diary, Grievance). Role names follow the manuals.

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `fo.da_accounts` | Dealing Assistant / SSA (Accounts) — claims, IDS, member records, VDR, Appendix-E | Login (FO Interface) | Core | ✔ (caseworker) | PEN, FIA, WSU, MAP |
| `fo.da_compliance` | Dealing Assistant (Compliance) — establishment files, inspections, 14B/7Q knock-off | Login | Core | ➕ | FIA, CMP |
| `fo.ss` | Section Supervisor (Accounts / Compliance) | Login | Core | ➕ | FIA, WSU, MAP |
| `fo.ao` | Accounts Officer | Login | Core | ➕ | PEN, FIA, MAP |
| `fo.fa_accounts` | DA / SS in the F&A (Accounts) wing — ledger debit posting, viewing the **Claim Approval Dockets (CAD)** of each level, reconciliation of rejected / returned payments | Login (FO Interface, Accounts wing) | Core | ➕ | SS, FIA, FRM |
| `fo.apfc` | APFC / RPFC-II — circle officer, accounts or compliance head, quasi-judicial authority (7A, 14B, 7Q) | Login + e-Proceedings | Core | ✔ (approving officer) | CMP, FIA, PEN |
| `fo.rpfc1` | RPFC-I — regional head of wings | Login | Core | ➕ | CMP, PEN, AUD |
| `fo.oic` | Officer-in-Charge of the office | Login | Core | ➕ | FIA, WSU, AUD |
| `fo.cash` | Cashier / Cash branch | Login | Core | ➕ | MAP (37), FRM |
| `fo.diary` | Diary / Receipt section (physical documents, inter-section diary) | Login (diary module) | Core | — | PEN |
| `fo.pro_intake` | PRO counter inwarding officer — inwards claims at the PRO counter (physical dockets, death-certificate checks, UAN registration problems surfaced at intake) | Login (PRO module of the field-office application) | Core | ➕ | SS, PEN |
| `fo.da_pension` | DA (Pension) — worksheet, PPO, transfer-in, Special 10D | Login | Core | ➕ | PEN |
| `fo.ss_pension` | SS (Pension) | Login | Core | ➕ | PEN |
| `fo.apfc_pension` | APFC / AC (Pension) — PPO approval and e-sign, DLC monitoring | Login | Core | ➕ | PEN |
| `fo.pension_disbursement` | Pension Disbursement Section | Login | Core (moves to CPPS) | — | PEN, REF |
| `fo.eo` | Enforcement Officer | Via e-Office + FO | Core → becomes `fo.icf` | ➕ | ICF, CMP, MAP |
| `fo.icf` | **Inspector-cum-Facilitator** (replaces EO under the Labour Codes; web-based inspection scheme) | New | **New** | ➕ | ICF (225 mentions) |
| `fo.recovery_officer` | Recovery Officer (8B–8G recovery, attachment, arrest warrants) | Via e-Office | Core | ➕ | REC (252 mentions) |
| `fo.legal` | Legal Cell (court cases, CGIT appeals) | Via e-Office | Core | ➕ | SOP-B, CMP |
| `fo.exemption` | Exemption cell (supervising PF trusts) | Via e-Office | Core | — | EXM |
| `fo.edli` | EDLI claims handling | Login | Core | — | EDLI |
| `fo.iw` | International-worker (IWU) processing at the RO | Login (IWU portal, EPFO role) | Core | — | EC, MAP |
| `fo.pro` | PRO / Facilitation centre / grievance cell | Login (EPFiGMS office) | Core | ➕ | EC, MAP, OUL |
| `fo.nan` | Nidhi Aapke Nikat outreach camp team | None | New | — | PEN, ICF |
| `fo.admin` | Office administration / HR / physical facilities | Login (HR Soft, e-Office) | Read | — | OUL |

## D. District Office (DO)

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `do.incharge` | District Office in-charge | Mostly via the parent RO's systems; no separate DO screens found | **New** — jurisdiction-scoped queues, facilitation, inspections, district dashboards | ✔ (district caseworker) | CMP (18), SOP-B (11), EC |
| `do.staff` | District Office facilitation and compliance staff | Via RO | **New** | — | CMP |

## E. Zonal Office (ZO)

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `zo.acc` | Additional Central PF Commissioner (Zone head) | Via e-Office, MIS | **New** — zone dashboards, escalations, approvals above RO limits | ✔ (zonal supervisor) | EC, SOP-B, EXM |
| `zo.rpfc1` | RPFC-I at the Zonal Office (zonal authority for freezing categories B and C; zone-level monitoring) | Via e-Office, email | **New** — zone queues and approvals | ➕ | FIA |
| `zo.rpfc1_audit` | RPFC-I (Audit) and **Zonal Concurrent Audit Cell (CAC)** — daily download from the Audit Portal, alerts to ROs | Login (Audit Portal) | Core | ➕ | AUD |
| `zo.internal_audit` | Internal audit parties auditing ROs | Via e-Office | **New** — audit workpapers and paras in system | ➕ | AUD |
| `zo.vigilance` | **Zonal Vigilance Directorate** | Via e-Office | **New** — restricted case access | ✔ | MAP, EC |
| `zo.fraud_committee` | Zonal / regional fraud-risk management committee (ZFRMC / RFRMC) | Via email / e-Office | **New** | — | FIA |
| `zo.zti` | Zonal Training Institute | None | Read (training sandbox) | — | EC (38), AUD |

## F. Head Office (HO) — leadership and divisions

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `ho.cpfc` | Central Provident Fund Commissioner | Via e-Office, MIS | Read + approvals | ✔ (HO analyst) | MAP, EC |
| `ho.acc_hq` | ACC (HQ) and HO division heads | Via e-Office | Read + policy approvals | — | EC, SOP-B |
| `ho.fa_cao` | FA & CAO — Finance & Accounts, **FIA vertical** (freezing category A), Balance Sheet cell | Via e-Office | Core | ➕ | FIA, EC, MAP |
| `ho.compliance` | Compliance Division | Via e-Office | Core (policy, e-Proceedings oversight) | — | CMP |
| `ho.recovery` | Recovery Division / Current Recovery vertical | Via e-Office | Core | — | REC |
| `ho.legal` | Legal Division | Via e-Office | Core | — | SOP-B |
| `ho.exemption` | Exemption Division | Via e-Office | Core | — | EXM |
| `ho.pension` | Pension Division (verticals: policy, EPS implementation, grievances, pension finance / audit / actuarial, EDLI) | Via e-Office | Core | — | PEN |
| `ho.edli` | EDLI Division | Via e-Office | Core | — | EDLI |
| `ho.audit` | Audit Division (internal audit, concurrent audit, IT audit, pre-audit) | Login (Audit Portal) | Core | ✔ (independent auditor) | AUD (39) |
| `ho.caiu` | Central Analysis & Intelligence Unit | Login (CAIU portal) | Core | ✔ | OUL, SOP-B, EC |
| `ho.iwu` | International Workers Unit | Login (IWU portal) | Core | — | EC, MAP |
| `ho.is` | IS Division (application ownership, Issue Tracker, block / unblock) | Login | Core | ➕ | FIA, PEN, EC |
| `ho.customer_service` | Customer Service / Public Grievances cell | Login (EPFiGMS office) | Core | — | EC |
| `ho.hr` | HR / HRM Wing | Login (HR Soft) | Read (HRM interface) | ✔ (HRM employee) | OUL, EC |
| `ho.investment` | Investment / IMC division | Via e-Office | Read (fund data) | — | EC |
| `ho.actuarial` | Actuarial unit | Via data extracts | Read | — | PEN |
| `ho.publicity` | Publicity / PR division | None | Read | — | EC |
| `ho.cvo` | **Chief Vigilance Officer** and **Director (Vigilance)** | Via e-Office | **New** — vigilance case management, restricted evidence access | ✔ (vigilance investigator) | MAP, EC |
| `ho.security` | Information security / SOC (cyber incidents, access reviews) | None found | **New** | ✔ (security analyst) | — |
| `ho.data_protection` | Data-protection / privacy officer (DPDP Act obligations) | None found | **New** | — | — |

## G. Governance and oversight bodies

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `gov.cbt` | Central Board of Trustees (tripartite; chaired by the Labour Minister) | Board papers | Read (board dashboards) | — | EC (196), MAP, EXM |
| `gov.ec` | Executive Committee of the CBT | Board papers | Read | — | EC |
| `gov.fiac` | Finance, Investment & Audit Committee | Board papers | Read | — | EC |
| `gov.peic` | Pension & EDLI Implementation Committee | Board papers | Read | — | PEN |
| `gov.mole` | Ministry of Labour & Employment | Reports, MIS | Read (aggregate, no PII) | ✔ (ministry viewer) | EC (49), MAP, REF |
| `gov.pmvbry_admin` | Incentive-scheme reconciler for PMVBRY (and legacy PMRPY / ABRY) — validates employment-linked incentives computed from ECR data | Scheme portal / MIS | Core | ➕ | SS, WEB |
| `gov.parliament` | Parliament (questions answered through MoLE) | Via MoLE | Read (aggregates) | — | MAP, REF |
| `gov.cag` | Comptroller & Auditor General | Via Audit Division | Read (audit access) | — | AUD, EC |
| `gov.statutory_auditor` | Statutory / attest auditors | Via Audit Division | Read | — | AUD |

## H. Technology and national operations

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `tech.ndc` | **National Data Centre**, Dwarka (G-NOC, application hosting, batch jobs) | Internal | Core | ✔ (NDC operator) | AUD, PEN, EXM |
| `tech.adc` | **Alternate Data Centre**, Secunderabad (disaster recovery site; part of G-NOC with NDC) | Internal | **Core (DR operations)** | ➕ | MAP/AUD ("Alternate Data centre-Secunderabad"), WEB |
| `tech.cpps` | **CPPS / Central Payment and Reconciliation Centre** at NDC (pan-India pension disbursement, sponsor-bank reconciliation) | Internal | Core | ➕ | PEN, REF |
| `tech.epfo3` | EPFO 3.0 core-banking platform and auto-settlement engine (a system actor making automated decisions) | Rolling out | Core (system actor; every automated decision audited) | — | REF |
| `tech.batch.annual_accounts` | Annual-accounts batch engine — year-end interest crediting; holds an exclusive lock on each member ledger while it runs (claims are blocked meanwhile) | Internal system actor | Core | ➕ | SS, MAP |
| `tech.ai_service` | AI / analytics service account (advisory only) | None | New | ✔ | `init.md` §8 |

## I. Training

| ID | Stakeholder | Today | Future | POC | Src |
|---|---|---|---|---|---|
| `train.pdnasa` | PDNASA — national training academy | None | Read (training sandbox with synthetic data) | — | EC, AUD |
| `train.zti` | Zonal Training Institutes | None | Read (training sandbox) | — | EC |

## J. External institutions and systems

| ID | Stakeholder | Role for EPFO | Future | Src |
|---|---|---|---|---|
| `ext.collecting_bank` | Agency / collecting banks and payment gateway | Challan payment, receipts, returns | Ext | MAP (92) |
| `ext.pension_bank` | Pension disbursing banks and link branches; CPPS sponsor bank | Pension credit, paid statements | Ext | PEN, REF |
| `ext.uidai` | UIDAI (Aadhaar e-KYC, OTP, face authentication) | Identity | Ext | JD, PEN, REF |
| `ext.npci` | NPCI (bank-account validation, payment rails) | Bank verification | Ext | — (no manual mention; standard for bank validation) |
| `ext.income_tax` | Income Tax Department / CBDT (PAN verification, TDS, Form 16A) | Tax | Ext | EC, MAP |
| `ext.mca` | Ministry of Corporate Affairs (SPICe+ / AGILE-PRO auto-registration, CIN) | Employer registration | Ext | CMP, REF |
| `ext.gstn` | GSTN (GSTIN verification) | Employer KYC | Ext | EC |
| `ext.shram_suvidha` | Shram Suvidha portal (common registration and inspection) | Employer registration, inspections | Ext | CMP, ICF, REF |
| `ext.umang` | UMANG (NeGD) mobile channel | Member / pensioner channel | Ext | EC, PEN, REF |
| `ext.jeevan_pramaan` | Jeevan Pramaan (Digital Life Certificate) | Pensioner liveness | Ext | PEN (24) |
| `ext.digilocker` | DigiLocker (documents, PPO / UAN card) | Documents | Ext | — (no manual mention) |
| `ext.ippb` | India Post / IPPB (doorstep DLC) | Pensioner service | Ext | PEN |
| `ext.cpgrams` | CPGRAMS (DARPG grievance portal) | Grievances routed in | Ext | EC |
| `ext.foreign_ss` | Foreign social-security liaison agencies (IWU portal "FOREIGN AGENCIES" login) | CoC verification, totalisation | Ext | EC, IWU |
| `ext.fund_manager` | Portfolio / fund managers and custodian | Investment operations | Ext (read-only feeds) | EC, EXM |
| `ext.actuary` | External actuary (EPS valuation) | Valuation data | Ext | PEN, EC |
| `ext.insurer` | LIC / insurer (EDLI history, annuity) | Insurance | Ext | MAP |
| `ext.cgit` | CGIT / EPF Appellate Tribunal (7-I appeals) | Appeals | Ext | EC, CMP |
| `ext.courts` | High Courts / Supreme Court | Litigation, orders | Ext | EC, CMP, EXM |
| `ext.cert_in` | CERT-In | Cyber-incident reporting | Ext | — (no manual mention) |

---

## Summary

| Group | Stakeholders | Of which new / future system roles |
|---|---|---|
| A. Members, beneficiaries, public | 11 | — |
| B. Employers and intermediaries | 11 | trust auditor, payroll provider, CSC operator, liquidator |
| C. Field office (RO / SRO) | 25 | Inspector-cum-Facilitator, NAN camp team |
| D. District Office | 2 | both |
| E. Zonal Office | 7 | ACC dashboards, internal audit, zonal vigilance, fraud committee |
| F. Head Office | 21 | CVO / vigilance, security / SOC, data protection |
| G. Governance and oversight | 9 | read-only dashboards for all |
| H. Technology and national ops | 6 | ADC DR operations, EPFO 3.0 system actor |
| I. Training | 2 | training sandbox |
| J. External | 20 | adapters |
| **Total** | **114** | |

The current POC (`init.md` §6.2) seeds 19 personas. The ➕ rows are the personas to add if the activity map shows they need their own endpoints.

## Open questions for an EPFO domain owner

1. **District Office:** what a DO decides on its own versus what it forwards to its RO.
2. **Zonal Office:** which approvals sit with the ACC (for example claims or freezing above RO limits) versus monitoring only.
3. **Vigilance and CAIU:** where their evidence access starts and ends, and how a CAIU signal becomes a vigilance case.
4. **ADC:** does it only host standby replicas, or does it run live workloads (e.g. read traffic, batch jobs)?
5. **EPFO 3.0:** which decisions are automated (auto-settlement), and who owns overriding or reviewing them.

## Sources

| Key | Document |
|---|---|
| MAP | *Manual of Accounting Procedure, Part I* — `pmvbry.epfindia.gov.in/wp-content/uploads/2025/11/MAP_PartI_Complete.pdf` |
| AUD | *Audit Manual* (08/12/2023) — `…/2025/11/Audit_Manual_08122023.pdf` |
| CMP | *Compliance Manual* (05/02/2024) — `…/2025/11/ComplianceManual.pdf` |
| REC | *Recovery Manual* (08/12/2023) — `…/2025/11/Recovery_Manual_08122023.pdf` |
| EXM | *Exemption Division Manual* (04/12/2023) and the SOPs on grant, management and regulation, cancellation and surrender — `pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/07/Exemption_Manual_04122023-2.pdf` (from `pmvbry.epfindia.gov.in/exempted-establishments`) |
| PMV | *Pradhan Mantri Viksit Bharat Rozgar Yojana — Guidelines* (M/o L&E, 16/08/2025) — `pmvbry.epfindia.gov.in/wp-content/themes/epfo-child/assets/images/PMVBRY-Final.pdf`; EPFO, *SOP for calculating incentives* — `pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/11/SOP-for-Calculation-of-Incentives.pdf` |
| PEN | *Pension Manual* — `…/2025/11/Pension_Manual.pdf` |
| EDLI | *EDLI Manual* — `…/2025/11/EDLI_Manual.pdf` |
| SOP-B | *Part B — SOPs and Service Standards* — `…/2025/11/PARTB_SOP_AND_STs_1.pdf` |
| ICF | *Manual for Inspector-cum-Facilitator* — `pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/08/Manual_for_Inspector_cum_Facilitator.pdf` |
| EC | *Agenda, 98th Executive Committee meeting* — `…/2025/12/EC_meeting_Agenda_98th.pdf` |
| JD | *SOP JD/2024/1 v3: Member profile correction* — `…/2025/09/Circular_WSU_01082024-1.pdf` |
| WSU | *SOP 01/2024 v2: Transaction-less and inoperative accounts* — `…/2025/09/Circular_SOP_WSU_02082024-5.pdf` |
| FIA | *SOP FIA/2023/1: Freezing / de-freezing* (see `portal-functions-by-login.md`) |
| OUL | EPFO, *Logins for Office Use* — `pmvbry.epfindia.gov.in/for_office_use/logins-of-office-use/` (EPFiGMS office, FO Interface, CAIU, Compliance e-Proceedings, eSamiksha, HR Soft, e-Office, NIC e-mail) |
| REF | PIB, *EPFO Reforms*, 12 Feb 2026 — `pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2026/03/EPFO-REFORMS-Posted-On-12-Feb-2026.pdf` |
| FRM | EPFO *Success stories* — RO Bengaluru Central, *Fraud risk mitigation* (VDR-ECR process) — `epfindia.gov.in/site_docs/PDFs/Updates/Success_Story_EPFO.pdf` (archived) |
| IWU | EPFO circular, *International Workers online CoC system* — `epfindia.gov.in/site_docs/PDFs/Circulars/Y2017-2018/IWU_OnlineSystem_COC_10677.pdf` (read by Codex) |
| SS | EPFO *Samadhan Setu* issue tracker extract, 24-Sep-2026 (`../samadhan-setu files/`: `samadhan_setu_parsed_issues.json`, `SAMADHAN_SETU_KNOWLEDGE_BASE.md`, `PF_LIFE_INTEGRATION_SPECIFICATION.md`). Module names and error texts are primary evidence; the knowledge base's narrative is secondary |
| WEB | ADC: public listings for "Alternate Data Centre (ADC) EPFO, Begumpet, Hyderabad"; PIB release on EPFO's G-NOC (NDC Dwarka + ADC Secunderabad) |
