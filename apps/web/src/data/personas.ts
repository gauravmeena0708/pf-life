/** Seeded personas (infra/keycloak/realm-epfo-demo.json, init.md §6.2.1). Password for all: Demo@2026! (demo only). */
export const PERSONA_GROUPS = [
  "Members and public", "Employers", "Field office",
  "Zone, head office and oversight", "Technology and external",
] as const;
export type PersonaGroup = typeof PERSONA_GROUPS[number];

export interface Persona {
  username: string;
  label: string;
  role: string;
  group: PersonaGroup;
  description: string;
}

export const DEMO_PASSWORD = "Demo@2026!";

export const PERSONAS: Persona[] = [
  { username: "member-a", label: "Member A", role: "member", group: "Members and public", description: "Active contributor — passbook, claims and grievances through the office." },
  { username: "member-b", label: "Member B", role: "member", group: "Members and public", description: "A second member — privacy checks, account recovery and an older linked UAN." },
  { username: "member-c", label: "Member C (left employment)", role: "member", group: "Members and public", description: "Left employment — final settlement, Form 10C withdrawal benefit and TDS." },
  { username: "member-d", label: "Member D (two member IDs)", role: "member", group: "Members and public", description: "Two member IDs — transfer previous service to the primary member ID." },
  { username: "member-e", label: "Member E (retired, pension)", role: "member", group: "Members and public", description: "Retired member — Form 10D pension application through to the PPO." },
  { username: "member-f", label: "Member F (Aadhaar not verified)", role: "member", group: "Members and public", description: "Aadhaar not verified — claims wait for the employer's attestation." },
  { username: "member-g", label: "Member G (changed jobs, auto-transfer)", role: "member", group: "Members and public", description: "Changed jobs — auto-transfer of the old member ID." },
  { username: "member-h", label: "Member H (higher pension option)", role: "member", group: "Members and public", description: "In service since 2011 above the wage ceiling — joint option for higher pension." },
  { username: "worker-expat", label: "International worker", role: "member", group: "Members and public", description: "Foreign national employed in India — international-worker coverage." },
  { username: "pensioner-a", label: "Pensioner A", role: "pensioner", group: "Members and public", description: "Pension payments, life certificates, bank changes and declarations." },
  { username: "claimant-a", label: "Claimant (nominee of a deceased member)", role: "claimant", group: "Members and public", description: "Nominee of a deceased member — PF, family pension and EDLI claims." },
  { username: "emp-owner", label: "Employer owner", role: "employer.owner", group: "Employers", description: "Verify an establishment, manage operators and signatories, and register changes." },
  { username: "emp-preparer", label: "Payroll preparer", role: "employer.operator", group: "Employers", description: "Prepare and validate monthly, arrear and supplementary returns." },
  { username: "emp-signatory", label: "Authorised signatory", role: "employer.signatory", group: "Employers", description: "Approve and submit returns, pay challans and attest member requests." },
  { username: "principal-owner", label: "Principal employer", role: "employer.owner", group: "Employers", description: "Demo Engineering Works: watch the demo establishment's remittances as its contractor." },
  { username: "do-caseworker", label: "District caseworker (DA)", role: "fo.da_accounts", group: "Field office", description: "Scrutinise claims, generate dockets and recommend decisions." },
  { username: "ro-ss", label: "Section supervisor", role: "fo.ss", group: "Field office", description: "Check claim recommendations and approve demand adjustments." },
  { username: "ro-ao", label: "Accounts officer", role: "fo.ao", group: "Field office", description: "Approve claims and pension Input Data Sheets; send back for corrections." },
  { username: "ro-apfc", label: "Regional approving officer (APFC)", role: "fo.apfc", group: "Field office", description: "Approve higher-band claims, establishment coverage and payment re-issues." },
  { username: "ro-oic", label: "Officer-in-charge", role: "fo.oic", group: "Field office", description: "Review office work, release ledger locks and reply to audit alerts." },
  { username: "ro-cashier", label: "Cashier", role: "fo.cash", group: "Field office", description: "Pay claims, reconcile payment scrolls and handle simulated bank returns." },
  { username: "ro-fa-accounts", label: "Accounts wing (F&A, CAD)", role: "fo.fa_accounts", group: "Field office", description: "Inspect Claim Approval Dockets, including tax and net amounts." },
  { username: "ro-pro", label: "Grievance officer / PRO", role: "fo.pro", group: "Field office", description: "Reply to grievances, link evidence and transfer cases between offices." },
  { username: "ro-pro-counter", label: "PRO counter (physical claims)", role: "fo.pro_intake", group: "Field office", description: "Inward physical claims and life certificates at the PRO counter." },
  { username: "ro-da-compliance", label: "DA Compliance (OLRE scrutiny)", role: "fo.da_compliance", group: "Field office", description: "Scrutinise OLRE registrations, defaulters, demands and VISHWAS cases." },
  { username: "iw-officer", label: "International Workers cell (CoC)", role: "fo.iw", group: "Field office", description: "Review and decide Certificates of Coverage for international workers." },
  { username: "ho-iwu", label: "HO International Workers Unit", role: "ho.iwu", group: "Zone, head office and oversight", description: "Maintain the synthetic social-security agreement catalogue." },
  { username: "ro-edli", label: "EDLI section officer", role: "fo.edli", group: "Field office", description: "Review death claims and record the EDLI benefit decision." },
  { username: "ho-publicity", label: "HO Public Relations (circulars)", role: "ho.publicity", group: "Zone, head office and oversight", description: "Publish circulars and their superseding versions." },
  { username: "ro-exemption", label: "Exemption cell (surrendered trusts)", role: "fo.exemption", group: "Field office", description: "Bring balances from surrendered PF trusts into member accounts." },
  { username: "zo-audit", label: "Concurrent Audit Cell (zone)", role: "zo.rpfc1_audit", group: "Zone, head office and oversight", description: "Inspect concurrent audit extracts and raise alerts to regional offices." },
  { username: "ndc-is", label: "NDC IS Division (Issue Tracker)", role: "ho.is", group: "Technology and external", description: "Execute approved freezes and de-freezes through the Issue Tracker." },
  { username: "zo-fraud", label: "Zonal fraud-risk committee", role: "zo.fraud_committee", group: "Zone, head office and oversight", description: "Review zonal fraud-risk cases and evidence of account freezes." },
  { username: "do-oic", label: "District Office in charge", role: "do.incharge", group: "Field office", description: "View the district dashboard and jurisdiction-scoped work queue." },
  { username: "ro-pension", label: "APFC (Pension)", role: "fo.apfc_pension", group: "Field office", description: "Approve pension worksheets and revisions, e-sign PPOs and prepare BRS." },
  { username: "ro-da-pension", label: "Dealing assistant (Pension)", role: "fo.da_pension", group: "Field office", description: "Prepare pension worksheets, issue PPOs and dispatch approved pensions." },
  { username: "ro-ss-pension", label: "Section supervisor (Pension)", role: "fo.ss_pension", group: "Field office", description: "Check initial pension arrears before the PPO is signed." },
  { username: "ro-pension-disbursement", label: "Pension disbursement", role: "fo.pension_disbursement", group: "Field office", description: "Legacy bank-wise pension disbursement lists, until CPPS pays centrally." },
  { username: "zo-acc", label: "Zonal supervisor (ACC)", role: "zo.acc", group: "Zone, head office and oversight", description: "Resolve escalated grievances and review zonal metrics." },
  { username: "zo-rpfc", label: "Zonal RPFC-I (freeze orders)", role: "zo.rpfc1", group: "Zone, head office and oversight", description: "Order establishment freezes and supervise zonal work." },
  { username: "ho-policy", label: "HO policy drafter (ACC HQ)", role: "ho.acc_hq", group: "Zone, head office and oversight", description: "Draft and submit versioned policy rules for approval." },
  { username: "ho-analyst", label: "Head Office analyst", role: "ho.cpfc", group: "Zone, head office and oversight", description: "Approve and publish policy rules; inspect aggregate dashboards." },
  { username: "ho-finance", label: "HO finance (FA & CAO)", role: "ho.fa_cao", group: "Zone, head office and oversight", description: "Record the annual interest rate and run illustrative interest crediting." },
  { username: "ndc-operator", label: "NDC operator", role: "tech.ndc", group: "Technology and external", description: "Demonstrate national data-centre operations and technical access." },
  { username: "ndc-cpps", label: "CPPS operator (NDC)", role: "tech.cpps", group: "Technology and external", description: "Run pension disbursements and reconcile the simulated sponsor bank." },
  { username: "ministry-viewer", label: "Ministry aggregate viewer", role: "gov.mole", group: "Zone, head office and oversight", description: "View aggregate reports and the published defaulter list." },
  { username: "b2b-client", label: "B2B payroll client", role: "payroll_provider", group: "Technology and external", description: "Demonstrate payroll-provider access through simulated integrations." },
  { username: "caiu-investigator", label: "CAIU investigator", role: "ho.caiu", group: "Zone, head office and oversight", description: "Review synthetic risk signals and record evidence-based dispositions." },
  { username: "hrm-employee", label: "HRM employee", role: "ho.hr", group: "Zone, head office and oversight", description: "Manage staff postings that determine officers’ jurisdictions." },
  { username: "security-analyst", label: "Security analyst", role: "ho.security", group: "Zone, head office and oversight", description: "Inspect request activity, sessions, recovery and security incidents." },
  { username: "vigilance-investigator", label: "Chief Vigilance Officer", role: "ho.cvo", group: "Zone, head office and oversight", description: "Assign preliminary inquiries into vigilance referrals and decide on the findings." },
  { username: "csc-operator", label: "CSC operator", role: "csc_operator", group: "Members and public", description: "Allot a UAN for a person at a Common Service Centre (mock Aadhaar face authentication)." },
  { username: "zo-vigilance", label: "Zonal vigilance", role: "zo.vigilance", group: "Zone, head office and oversight", description: "Inquire into vigilance cases assigned to the zone and report findings." },
  { username: "ho-actuarial", label: "HO actuarial cell", role: "ho.actuarial", group: "Zone, head office and oversight", description: "De-identified EPS extract for the actuarial valuation." },
  { username: "zo-internal-audit", label: "Zonal internal audit", role: "zo.internal_audit", group: "Zone, head office and oversight", description: "Audit a regional office and raise paras for it to answer." },
  { username: "ho-dpo", label: "Data protection officer", role: "ho.data_protection", group: "Zone, head office and oversight", description: "Answer members' requests about their personal data (DPDP Act)." },
  { username: "statutory-auditor", label: "Statutory auditor", role: "gov.statutory_auditor", group: "Zone, head office and oversight", description: "Attest audit of the accounts (read-only)." },
  { username: "ho-investment", label: "HO investment cell", role: "ho.investment", group: "Zone, head office and oversight", description: "Fund and investment reporting." },
  { username: "cbt-member", label: "CBT member", role: "gov.cbt", group: "Zone, head office and oversight", description: "Central Board of Trustees member — board packs." },
  { username: "fiac-member", label: "FIAC member", role: "gov.fiac", group: "Zone, head office and oversight", description: "Finance, Investment and Audit Committee member — board packs and investments." },
  { username: "auditor", label: "Independent auditor", role: "ho.audit", group: "Zone, head office and oversight", description: "Inspect the audit log, verify its hash chain and trace request events." },
];
