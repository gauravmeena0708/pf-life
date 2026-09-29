/** Seeded personas (infra/keycloak/realm-epfo-demo.json, init.md §6.2.1). Password for all: Demo@2026! (demo only). */
export interface Persona {
  username: string;
  label: string;
  role: string;
}

export const DEMO_PASSWORD = "Demo@2026!";

export const PERSONAS: Persona[] = [
  { username: "member-a", label: "Member A", role: "member" },
  { username: "member-b", label: "Member B", role: "member" },
  { username: "member-c", label: "Member C (left employment)", role: "member" },
  { username: "member-d", label: "Member D (two member IDs)", role: "member" },
  { username: "member-e", label: "Member E (retired, pension)", role: "member" },
  { username: "pensioner-a", label: "Pensioner A", role: "pensioner" },
  { username: "claimant-a", label: "Claimant (nominee of a deceased member)", role: "claimant" },
  { username: "emp-owner", label: "Employer owner", role: "employer.owner" },
  { username: "emp-preparer", label: "Payroll preparer", role: "employer.operator" },
  { username: "emp-signatory", label: "Authorised signatory", role: "employer.signatory" },
  { username: "do-caseworker", label: "District caseworker (DA)", role: "fo.da_accounts" },
  { username: "ro-ss", label: "Section supervisor", role: "fo.ss" },
  { username: "ro-ao", label: "Accounts officer", role: "fo.ao" },
  { username: "ro-apfc", label: "Regional approving officer (APFC)", role: "fo.apfc" },
  { username: "ro-oic", label: "Officer-in-charge", role: "fo.oic" },
  { username: "ro-cashier", label: "Cashier", role: "fo.cash" },
  { username: "ro-fa-accounts", label: "Accounts wing (F&A, CAD)", role: "fo.fa_accounts" },
  { username: "ro-pro", label: "Grievance officer / PRO", role: "fo.pro" },
  { username: "ro-pro-counter", label: "PRO counter (physical claims)", role: "fo.pro_intake" },
  { username: "ro-da-compliance", label: "DA Compliance (OLRE scrutiny)", role: "fo.da_compliance" },
  { username: "ro-pension", label: "APFC (Pension)", role: "fo.apfc_pension" },
  { username: "ro-da-pension", label: "Dealing assistant (Pension)", role: "fo.da_pension" },
  { username: "ro-ss-pension", label: "Section supervisor (Pension)", role: "fo.ss_pension" },
  { username: "zo-acc", label: "Zonal supervisor (ACC)", role: "zo.acc" },
  { username: "zo-rpfc", label: "Zonal RPFC-I (freeze orders)", role: "zo.rpfc1" },
  { username: "ho-policy", label: "HO policy drafter (ACC HQ)", role: "ho.acc_hq" },
  { username: "ho-analyst", label: "Head Office analyst", role: "ho.cpfc" },
  { username: "ho-finance", label: "HO finance (FA & CAO)", role: "ho.fa_cao" },
  { username: "ndc-operator", label: "NDC operator", role: "tech.ndc" },
  { username: "ndc-cpps", label: "CPPS operator (NDC)", role: "tech.cpps" },
  { username: "ministry-viewer", label: "Ministry aggregate viewer", role: "gov.mole" },
  { username: "b2b-client", label: "B2B payroll client", role: "payroll_provider" },
  { username: "caiu-investigator", label: "CAIU investigator", role: "ho.caiu" },
  { username: "hrm-employee", label: "HRM employee", role: "ho.hr" },
  { username: "security-analyst", label: "Security analyst", role: "ho.security" },
  { username: "vigilance-investigator", label: "Vigilance investigator", role: "ho.cvo" },
  { username: "auditor", label: "Independent auditor", role: "ho.audit" },
];
