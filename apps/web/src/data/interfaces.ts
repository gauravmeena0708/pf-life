/** The 21 interfaces of init.md §2.3 with coverage from docs/api-matrix.md. */
export type Coverage = "Working" | "Mock" | "Planned";

export interface InterfaceDef {
  id: number;
  slug: string;
  name: string;
  coverage: Coverage;
  stakeholders: string[];
}

export const INTERFACES: InterfaceDef[] = [
  { id: 1, slug: "public", name: "Public", coverage: "Working", stakeholders: ["public", "complainant", "rti_applicant"] },
  { id: 2, slug: "employer", name: "Employer", coverage: "Working", stakeholders: ["employer.owner", "employer.signatory", "employer.operator", "principal_employer", "contractor", "exempted.trust"] },
  { id: 3, slug: "member", name: "Member", coverage: "Working", stakeholders: ["member", "member.exited", "pensioner", "family_pensioner", "claimant"] },
  { id: 4, slug: "office", name: "Office", coverage: "Working", stakeholders: ["fo.da_accounts", "fo.ss", "fo.ao", "fo.cash", "fo.da_pension"] },
  { id: 5, slug: "grievance", name: "Grievance", coverage: "Working", stakeholders: ["fo.pro", "ho.customer_service"] },
  { id: 6, slug: "international", name: "International worker", coverage: "Mock", stakeholders: ["intl_worker", "fo.iw", "ho.iwu"] },
  { id: 7, slug: "district-office", name: "District office", coverage: "Working", stakeholders: ["do.incharge", "do.staff"] },
  { id: 8, slug: "regional-office", name: "Regional office", coverage: "Working", stakeholders: ["fo.apfc", "fo.rpfc1", "fo.oic"] },
  { id: 9, slug: "zonal-office", name: "Zonal office", coverage: "Working", stakeholders: ["zo.acc", "zo.rpfc1"] },
  { id: 10, slug: "head-office", name: "Head office", coverage: "Working", stakeholders: ["ho.cpfc", "ho.acc_hq", "ho.fa_cao"] },
  { id: 11, slug: "ndc", name: "NDC", coverage: "Working", stakeholders: ["tech.ndc", "tech.adc", "tech.cpps"] },
  { id: 12, slug: "ministry", name: "Ministry", coverage: "Working", stakeholders: ["gov.mole", "gov.parliament"] },
  { id: 13, slug: "b2b", name: "B2B", coverage: "Mock", stakeholders: ["payroll_provider", "ext.collecting_bank"] },
  { id: 14, slug: "caiu", name: "CAIU", coverage: "Working", stakeholders: ["ho.caiu"] },
  { id: 15, slug: "hrm", name: "HRM", coverage: "Working", stakeholders: ["ho.hr"] },
  { id: 16, slug: "reporting", name: "Reporting and monitoring", coverage: "Working", stakeholders: ["gov.cbt", "gov.ec", "gov.fiac", "gov.peic"] },
  { id: 17, slug: "security", name: "Security", coverage: "Working", stakeholders: ["ho.security", "ho.data_protection"] },
  { id: 18, slug: "vigilance", name: "Vigilance", coverage: "Planned", stakeholders: ["ho.cvo", "zo.vigilance"] },
  { id: 19, slug: "audit", name: "Audit", coverage: "Working", stakeholders: ["ho.audit", "zo.rpfc1_audit", "gov.cag"] },
  { id: 20, slug: "umang", name: "UMANG", coverage: "Working", stakeholders: ["ext.umang"] },
  { id: 21, slug: "ai", name: "AI model / local LLM", coverage: "Working", stakeholders: ["tech.ai_service"] },
];
