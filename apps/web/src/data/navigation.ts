/**
 * Menus per login, following the real EPFO portals (docs/portal-functions-by-login.md: member, employer and
 * pensioner menus from EPFO manuals and screenshots; field-office menu bars from live screenshots, §8.4).
 * An item with `to` opens the POC screen that does it; an item without `to` is a real menu this POC does not
 * build and is shown, not clickable. Official menu names stay as the portals spell them; POC-only screens use
 * `labelKey` (translated).
 */
export interface NavItem { label?: string; labelKey?: string; to?: string }
export interface NavGroup { label?: string; labelKey?: string; to?: string; items?: NavItem[] }

const link = (label: string, to?: string): NavItem => ({ label, to });

export const PUBLIC_SERVICES: NavItem[] = [
  link("Grievance (without login)", "/public/grievances#public-grievance-heading"),
  link("Grievance status", "/public/grievances#grievance-status-heading"),
  link("Claim status", "/public/claims#claim-status-heading"),
  link("Circulars", "/public/circulars#circulars-heading"),
];

const MEMBER: NavGroup[] = [
  { label: "View", items: [
    link("Profile", "/member/profile#member-profile-heading"), link("Service History", "/member/service#service-heading"),
    link("UAN Card", "/member/uan-card"), link("Passbook", "/member/passbook"), link("Annual statement and taxable interest", "/member/passbook#annual-statement-heading"), link("Pension estimate", "/member/profile#pension-estimate-heading")] },
  { label: "Manage", items: [
    link("Basic Details (Joint Declaration)", "/member/profile#correction-heading"), link("Contact Details", "/member/security#contact-heading"),
    link("KYC", "/member/kyc"), link("e-Nomination", "/member/nomination#nomination-heading"), link("Know your UAN", "/member/nomination#uan-lookup-heading"), link("Mark Exit", "/member/service#exit-heading")] },
  { label: "Account", items: [link("Change Password"), { labelKey: "navigation.accountSecurity", to: "/member/security" }] },
  { label: "Online Services", items: [
    link("Claim (Form-31, 19, 10C & 10D)", "/member/claims"), link("One Member – One EPF Account (Transfer Request)", "/member/service#transfer-heading"), link("Auto-transfer", "/member/service#auto-transfer-heading"),
    link("Track Claim Status", "/member/claims"), link("Download Annexure K", "/member/service#applications-heading"), link("Joint Declaration", "/member/profile#correction-heading"),
    link("Form 15G / 15H", "/member/claims#tax-declaration-heading"), link("Pension (Form 10D) / scheme certificate", "/member/pension"),
    link("Pension on higher wages", "/member/higher-pension#higher-pension-heading")] },
  { label: "PMVBRY" },
  { labelKey: "navigation.help", items: [{ labelKey: "navigation.grievances", to: "/member/grievances" }, { labelKey: "navigation.assistant", to: "/member/assistant" }] },
];

export function memberMenus(internationalWorker: boolean): NavGroup[] {
  return internationalWorker ? MEMBER.map((group) => group.label === "View"
    ? { ...group, items: [...group.items!, link("International worker coverage", "/international-worker")] } : group) : MEMBER;
}

const EMPLOYER: NavGroup[] = [
  { label: "Member", items: [
    link("Register-Individual", "/employer/registration#register-heading"), link("Register-Bulk", "/employer/registration#bulk-heading"), link("Member Profile (mark exit)", "/employer/members#exit-heading"), link("Approvals", "/employer/members#approvals-heading"),
    link("Approve KYC pending for Digital Signature", "/employer/registration#kyc-approvals-heading"),
    link("Approve KYC seeded by member", "/employer/registration#kyc-approvals-heading"), link("KYC Bulk", "/employer/registration#kyc-bulk-heading"),
    link("Exit correction", "/employer/members#exit-correction-heading"), link("Exit bulk upload", "/employer/members#exit-bulk-heading"),
    link("Missing details", "/employer/registration#missing-heading"), link("Member Location Mapping", "/employer/members#location-heading"), link("KYC Verification / PAN Verification", "/employer/registration#kyc-approvals-heading"),
    link("Joint Declaration requests", "/employer#jd-heading"), link("Employer-initiated JD", "/employer#employer-jd-heading")] },
  { label: "Establishment", items: [
    link("Establishment Profile", "/employer/establishment#est-config-heading"), link("Form 5A", "/employer/establishment#est-form5a-heading"),
    link("Branches (Form 2A)", "/employer/establishment#est-branches-heading"), link("Establishment KYC and bank accounts", "/employer/establishment#est-kyc-heading"),
    link("Contractors", "/employer/establishment#est-contractors-heading"),
    link("DSC/e-sign Registration", "/employer/establishment#esign-heading"), link("e-sign Registration", "/employer/establishment#esign-heading"),
    link("Authorized eSign List", "/employer/establishment#esign-heading")] },
  { label: "Payments", items: [
    link("ECR Upload", "/employer/ecr#ecr-prepare"), link("Return Filing", "/employer/ecr#ecr-returns"), link("Return monthly dashboard", "/employer/returns#returns-dashboard-heading"),
    link("Direct Challan", "/employer/returns#direct-challan-heading"), link("Demands (14B / 7Q)", "/employer/returns#demands-heading"), link("VISHWAS: settle damages", "/employer/returns#vishwas-heading"), link("Monthly Return for Exempted Establishment"), link("TRRN query / challan status", "/employer/ecr#ecr-challans")] },
  { label: "Dashboards", items: [link("Employer dashboard", "/employer#employer-dashboard-heading"), link("Compliance summary", "/employer/returns#compliance-summary-heading"), link("Active Members details", "/employer/registration#active-heading"), link("Missing details", "/employer/registration#active-heading")] },
  { label: "User", items: [link("Sub-users (payroll operators)", "/employer#people-operator")] },
  { label: "Admin" },
  { label: "Online Services", items: [link("Transfer Claims", "/employer/members#transfers-heading"), link("Claim attestations", "/employer/members#claim-attestations-heading"),
    link("Higher-pension joint-option validation", "/employer/members#higher-pension-validations-heading"), link("International workers (CoC)", "/employer/international")] },
  { label: "PMVBRY" },
  { label: "EEC-2026/VISHWAS" },
];

/** Field Office Interface: the top-level menus seen on live screens, grouped (the real bar wraps onto 2–3 rows). */
function fieldOffice(role: string): NavGroup[] {
  const queue = "/office/work-queue";
  return [
    { label: "Claims & settlement", items: [link("CLAIMS", queue), link("Online Services", queue),
      link("ANNEXURE K FILE", role === "fo.da_accounts" ? "/office/claim-tools#annexure-heading" : undefined),
      ...(["fo.da_accounts", "fo.ao"].includes(role) ? [link("Form 10D pension claims (IDS)", "/office/pension-claims")] : []),
      ...(role === "fo.fa_accounts" ? [link("Claim Approval Docket (CAD)", "/office/claim-tools#cad-heading")] : []),
      ...(role === "fo.cash" ? [link("Payment scroll", "/office/claim-tools#scroll-heading")] : []),
      ...(["fo.da_accounts", "fo.cash"].includes(role) ? [link("Unpaid returns: rejections", "/office/returns#office-returns-heading")] : []),
      ...(role === "fo.da_accounts" ? [link("Claim audit trail", "/office/claim-tools#trail-heading"), link("Stopped claims", "/office/work-queue#stopped-heading")] : []),
      ...(role === "fo.apfc" ? [link("Death claims: beneficiary shares", "/office/claim-tools#shares-heading")] : []),
      ...(role === "fo.pro_intake" ? [link("PRO counter: physical claims", "/office/pro-counter")] : [])] },
    { label: "Members", items: [link("Member", role === "fo.oic" ? queue : role === "fo.da_accounts" ? "/office/claim-tools#member360-heading" : undefined),
      link("Query"), ...(["fo.da_accounts", "fo.oic"].includes(role) ? [link("Inoperative accounts", "/office/claim-tools#inoperative-heading")] : []),
      ...(role === "fo.oic" ? [link("Ledger locks", "/office/claim-tools#locks-heading")] : [])] },
    { label: "Receipts & reconciliation", items: [
      role === "fo.apfc" ? link("ECR Approval") : link("VDR Vs ECR filing"), link("Reco - ECR Vs VDR"), link("VDR Member Beneficiary"),
      link("VDR Rejection", role === "fo.da_accounts" ? "/office/ledger#vdr-heading" : undefined),
      ...(["fo.cash", "fo.da_accounts"].includes(role) ? [link("Receipts outside the challan flow (VDR)", "/office/ledger#vdr-heading")] : []), ...["ANNEXURE K RECO", "ANNEXURE K VDR RECO"].map((l) => link(l, role === "fo.da_accounts" ? "/office/claim-tools#annexure-heading" : undefined))] },
    { label: "Establishments & compliance", items: [
      ...(["fo.da_compliance", "fo.apfc", "fo.oic"].includes(role) ? [link("Defaulters, cases and VISHWAS", "/office/compliance")] : []),
      link("7Q & 14B", ["fo.da_compliance", "fo.ss"].includes(role) ? "/office/returns#knock-off-heading" : undefined),
      link("Establishment", ["fo.oic", "fo.apfc"].includes(role) ? "/office/work-queue" : undefined),
      link("OLRE", ["fo.da_compliance", "fo.apfc"].includes(role) ? "/office/olre" : undefined),
      ...(role === "fo.apfc" ? [link("Establishment change requests", "/office/olre#est-changes-heading"), link("DSC / e-sign approvals", "/office/olre#sig-heading")] : []), link("Exempted-Unexempted", role === "fo.exemption" ? "/office/exempted" : undefined), link("Past Accum. File Upload", role === "fo.exemption" ? "/office/exempted#past-accumulation-heading" : undefined),
      link("PAST ACCUM BULK TRANSFER"), link("PAST ACCUM VDR RECO")] },
    { label: "Pension", items: [link("Pension"), link("NPPS")] },
    { label: "Accounts", items: [link("Annual Accounting"),
      ...(["fo.da_accounts", "fo.apfc"].includes(role) ? [link("Appendix E", "/office/ledger#appendix-e-heading")] : []),
      ...(role === "fo.da_accounts" ? [link("Reverse a journal / recredit a transfer", "/office/ledger#reversal-heading")] : [])] },
    { label: "Office", items: [...(role === "fo.oic" ? [link("Audit alerts", "/audit/concurrent#audit-alerts-heading"), link("Issue Tracker requests", "/audit/concurrent#issue-tracker-raise-heading")] : []), link("Dashboard", role === "fo.oic" ? "/dashboards" : undefined), link("Admin"), link("Services")] },
  ];
}

/** The DA (Pension) login shows a short bar: Services · NPPS · Pension · CLAIMS. */
const PENSION_OFFICE: NavGroup[] = [
  { label: "Services" }, { label: "NPPS" },
  { label: "Pension", items: [link("Pension claims (Form 10D)", "/office/pension-claims"), link("Pension revisions", "/office/pension-revisions"),
    link("Pension Enquiry Details", "/office/pensions#enquiry-heading"), link("CPPS runs and BRS", "/cpps"),
    link("Track Pension Claims Updation Activities", "/office/pensions#updation-heading"), link("Life certificates overdue", "/office/pensions#overdue-heading")] },
  { label: "CLAIMS", items: [link("Form 10D claims", "/office/pension-claims")] },
];

/** Pensioners' portal: public enquiries (no pensioner login exists; the POC adds one for the pension view). */
const PENSIONER: NavGroup[] = [
  { labelKey: "navigation.pension", to: "/pensioner" },
  { label: "Services", items: [link("Life certificate (Jeevan Pramaan)", "/pensioner/services#lc-heading"), link("PPO", "/pensioner/services#ppo-heading"),
    link("Pension slip", "/pensioner/services#slip-heading"), link("Change bank account", "/pensioner/services#bank-change-heading"),
    link("Declarations", "/pensioner/services#declarations-heading")] },
  { label: "Pensioners' Portal", items: [
    link("Jeevan Pramaan Enquiry", "/public#pension-enquiries"), link("Know your PPO No.", "/public#pension-enquiries"),
    link("PPO Enquiry / Payment Enquiry", "/pensioner#pension-payments-heading"), link("Know Your Pension Status", "/pensioner#monthly-pension-heading"),
    link("Know Your Pension Payee Bank")] },
];

/** A nominee or legal heir of a deceased member: no portal login exists (claims are filed on paper or via UMANG). */
const CLAIMANT: NavGroup[] = [
  { label: "Death claims", items: [link("PF claim (Form 20)", "/claimant#file-heading"), link("EDLI claim (Form 5IF)", "/claimant#file-heading"),
    link("Track claim / beneficiaries", "/claimant#claim-status-heading"), link("Composite claim (CCF)")] },
  { label: "Family pension (Form 10D)", to: "/claimant#family-pension-heading" },
];

/** Head office, zonal and oversight roles: no real menu is documented; the POC's own screens. */
function poc(role: string): NavGroup[] {
  const out: NavGroup[] = [];
  if (role === "zo.acc" || role === "zo.rpfc1") out.push({ labelKey: "navigation.workQueue", to: "/office/work-queue" });
  if (role === "zo.acc" || role === "ho.cpfc") out.push({ labelKey: "navigation.grievanceMetrics", to: "/monitoring/grievances" });
  if (["zo.acc", "ho.cpfc", "gov.mole"].includes(role)) out.push({ labelKey: "navigation.dashboards", to: "/dashboards" });
  if (["ho.acc_hq", "ho.cpfc", "ho.pension", "ho.audit"].includes(role)) out.push({ labelKey: "navigation.policy", to: "/policy" });
  if (role === "ho.fa_cao") out.push({ labelKey: "navigation.interest", to: "/finance/interest" }, { label: "Record the interest rate", to: "/finance/interest#interest-rate-record-heading" });
  if (role === "ho.publicity") out.push({ label: "Publish circulars", to: "/ho/circulars#publish-circular-heading" });
  if (role === "ho.security") out.push({ labelKey: "navigation.security", to: "/security/activity" }, { labelKey: "navigation.sessions", to: "/security/sessions" });
  if (role === "ho.security") out.push({ label: "Security incidents", to: "/security/activity#incidents-heading" });
  if (role === "zo.rpfc1_audit") out.push({ label: "Concurrent audit", to: "/audit/concurrent" });
  if (role === "ho.is") out.push({ label: "Issue Tracker", to: "/ndc/issue-tracker" });
  if (role === "zo.fraud_committee") out.push({ label: "Fraud-risk cases", to: "/zo/fraud-risk" });
  if (role === "do.incharge") out.push({ label: "District dashboard", to: "/do/dashboard" });
  if (role === "ho.hr") out.push({ label: "HRM", to: "/i/hrm" }, { label: "Staff postings", to: "/i/hrm#postings-heading" });
  if (role === "ho.caiu") out.push({ labelKey: "navigation.riskSignals", to: "/caiu/signals" });
  if (role === "ho.security" || role === "ho.audit") out.push({ labelKey: "navigation.audit", to: "/audit/log" });
  return out;
}

export function menusFor(role: string | undefined): NavGroup[] {
  if (!role || role === "public") return [{ labelKey: "navigation.publicLookups", items: PUBLIC_SERVICES }];
  if (role === "member") return MEMBER;
  if (role.startsWith("employer.")) return EMPLOYER;
  if (role === "pensioner") return PENSIONER;
  if (role === "claimant") return CLAIMANT;
  if (role === "fo.edli") return [{ label: "EDLI claims", to: "/office/edli-claims" }];
  if (role === "fo.iw") return [{ label: "Certificate of coverage queue", to: "/office/international#coc-queue-heading" }];
  if (role === "ho.iwu") return [{ label: "Social-security agreements", to: "/ho/agreements#agreements-heading" }];
  if (["fo.apfc_pension", "fo.da_pension", "fo.ss_pension"].includes(role)) return PENSION_OFFICE;
  if (role === "tech.cpps") return [{ label: "CPPS disbursement", to: "/cpps" }];
  if (role.startsWith("fo.")) return fieldOffice(role);
  return poc(role);
}

/** Where "Home" goes for a role. */
export function homeFor(role: string | undefined): string {
  if (role === "ho.security") return "/security/activity";
  if (role === "ho.audit") return "/audit/log";
  if (role === "ho.caiu") return "/caiu/signals";
  if (role === "ho.acc_hq") return "/policy";
  if (role === "ho.cpfc" || role === "gov.mole") return "/dashboards";
  if (role === "zo.acc" || role === "zo.rpfc1") return "/office/work-queue";
  if (role === "zo.rpfc1_audit") return "/audit/concurrent";
  if (role === "ho.is") return "/ndc/issue-tracker";
  if (role === "zo.fraud_committee") return "/zo/fraud-risk";
  if (role === "do.incharge") return "/do/dashboard";
  if (role === "ho.hr") return "/i/hrm";
  if (role === "member") return "/member/passbook";
  if (role?.startsWith("employer.")) return "/employer";
  if (role === "pensioner") return "/pensioner";
  if (role === "claimant") return "/claimant";
  if (role === "fo.edli") return "/office/edli-claims";
  if (role === "fo.iw") return "/office/international";
  if (role === "ho.iwu") return "/ho/agreements";
  if (role === "ho.publicity") return "/ho/circulars";
  if (role === "fo.exemption") return "/office/exempted";
  if (role === "ho.fa_cao") return "/finance/interest";
  if (role === "fo.pro_intake") return "/office/pro-counter";
  if (role === "fo.apfc_pension") return "/office/pension-revisions";
  if (role === "fo.da_pension" || role === "fo.ss_pension") return "/office/pension-claims";
  if (role === "tech.cpps") return "/cpps";
  if (role === "fo.da_compliance") return "/office/olre";
  if (role?.startsWith("fo.")) return "/office/work-queue";
  return "/";
}
