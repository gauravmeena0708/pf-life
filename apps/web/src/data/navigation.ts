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

const MEMBER: NavGroup[] = [
  { label: "View", items: [
    link("Profile", "/member/profile#member-profile-heading"), link("Service History", "/member/service#service-heading"),
    link("UAN Card", "/member/uan-card"), link("Passbook", "/member/passbook"), link("Pension estimate", "/member/profile#pension-estimate-heading")] },
  { label: "Manage", items: [
    link("Basic Details (Joint Declaration)", "/member/profile#correction-heading"), link("Contact Details", "/member/security#contact-heading"),
    link("KYC", "/member/kyc"), link("E-Nomination"), link("Mark Exit", "/member/service#exit-heading")] },
  { label: "Account", items: [link("Change Password"), { labelKey: "navigation.accountSecurity", to: "/member/security" }] },
  { label: "Online Services", items: [
    link("Claim (Form-31, 19, 10C & 10D)", "/member/claims"), link("One Member – One EPF Account (Transfer Request)", "/member/service#transfer-heading"),
    link("Track Claim Status", "/member/claims"), link("Download Annexure K", "/member/service#applications-heading"), link("Joint Declaration", "/member/profile#correction-heading"),
    link("Form 15G / 15H", "/member/claims#tax-declaration-heading"), link("Pension (Form 10D) / scheme certificate", "/member/pension")] },
  { label: "PMVBRY" },
  { labelKey: "navigation.help", items: [{ labelKey: "navigation.grievances", to: "/member/grievances" }, { labelKey: "navigation.assistant", to: "/member/assistant" }] },
];

const EMPLOYER: NavGroup[] = [
  { label: "Member", items: [
    link("Register-Individual", "/employer/registration#register-heading"), link("Register-Bulk", "/employer/registration#bulk-heading"), link("Member Profile (mark exit)", "/employer/members#exit-heading"), link("Approvals", "/employer/members#approvals-heading"),
    link("Approve KYC pending for Digital Signature", "/employer/registration#kyc-approvals-heading"),
    link("Approve KYC seeded by member", "/employer/registration#kyc-approvals-heading"), link("KYC Bulk", "/employer/registration#kyc-bulk-heading"), link("Exit-Bulk"),
    link("Missing details", "/employer/registration#missing-heading"), link("Member Location Mapping"), link("KYC Verification / PAN Verification", "/employer/registration#kyc-approvals-heading"),
    link("Joint Declaration requests", "/employer#jd-heading")] },
  { label: "Establishment", items: [
    link("Establishment Profile", "/employer#emp-heading"), link("Form 5A"), link("Branches (Form 2A)"),
    link("DSC/e-sign Registration"), link("e-sign Registration"), link("Authorized eSign List", "/employer#people-signatory")] },
  { label: "Payments", items: [
    link("ECR Upload", "/employer/ecr#ecr-prepare"), link("Return Filing", "/employer/ecr#ecr-returns"), link("Return monthly dashboard"),
    link("Direct Challan"), link("Monthly Return for Exempted Establishment"), link("TRRN query / challan status", "/employer/ecr#ecr-challans")] },
  { label: "Dashboards", items: [link("Active Members details", "/employer/registration#active-heading"), link("Missing details", "/employer/registration#active-heading")] },
  { label: "User", items: [link("Sub-users (payroll operators)", "/employer#people-operator")] },
  { label: "Admin" },
  { label: "Online Services", items: [link("Transfer Claims", "/employer/members#transfers-heading"), link("Claim attestation"), link("Higher-pension joint-option validation")] },
  { label: "PMVBRY" },
  { label: "EEC-2026/VISHWAS" },
];

/** Field Office Interface: the top-level menus seen on live screens, grouped (the real bar wraps onto 2–3 rows). */
function fieldOffice(role: string): NavGroup[] {
  const queue = "/office/work-queue";
  return [
    { label: "Claims & settlement", items: [link("CLAIMS", queue), link("Online Services", queue), link("ANNEXURE K FILE"),
      ...(["fo.da_accounts", "fo.ao"].includes(role) ? [link("Form 10D pension claims (IDS)", "/office/pension-claims")] : []),
      ...(role === "fo.fa_accounts" ? [link("Claim Authorization Document (CAD)", "/office/claim-tools#cad-heading")] : []),
      ...(role === "fo.cash" ? [link("Payment scroll", "/office/claim-tools#scroll-heading")] : []),
      ...(role === "fo.da_accounts" ? [link("Claim audit trail", "/office/claim-tools#trail-heading")] : []),
      ...(role === "fo.apfc" ? [link("Death claims: beneficiary shares", "/office/claim-tools#shares-heading")] : []),
      ...(role === "fo.pro_intake" ? [link("PRO counter: physical claims", "/office/pro-counter")] : [])] },
    { label: "Members", items: [link("Member", role === "fo.oic" ? queue : role === "fo.da_accounts" ? "/office/claim-tools#member360-heading" : undefined),
      link("Query"), ...(["fo.da_accounts", "fo.oic"].includes(role) ? [link("Inoperative accounts", "/office/claim-tools#inoperative-heading")] : [])] },
    { label: "Receipts & reconciliation", items: [
      role === "fo.apfc" ? link("ECR Approval") : link("VDR Vs ECR filing"), link("Reco - ECR Vs VDR"), link("VDR Member Beneficiary"),
      link("VDR Rejection"), link("ANNEXURE K RECO"), link("ANNEXURE K VDR RECO")] },
    { label: "Establishments & compliance", items: [
      link("Establishment"), link("OLRE"), link("7Q & 14B"), link("Exempted-Unexempted"), link("Past Accum. File Upload"),
      link("PAST ACCUM BULK TRANSFER"), link("PAST ACCUM VDR RECO")] },
    { label: "Pension", items: [link("Pension"), link("NPPS")] },
    { label: "Accounts", items: [link("Annual Accounting")] },
    { label: "Office", items: [link("Dashboard", role === "fo.oic" ? "/dashboards" : undefined), link("Admin"), link("Services")] },
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
  { label: "Family pension (Form 10D)" },
];

/** Head office, zonal and oversight roles: no real menu is documented; the POC's own screens. */
function poc(role: string): NavGroup[] {
  const out: NavGroup[] = [];
  if (role === "zo.acc" || role === "zo.rpfc1") out.push({ labelKey: "navigation.workQueue", to: "/office/work-queue" });
  if (role === "zo.acc" || role === "ho.cpfc") out.push({ labelKey: "navigation.grievanceMetrics", to: "/monitoring/grievances" });
  if (["zo.acc", "ho.cpfc", "gov.mole"].includes(role)) out.push({ labelKey: "navigation.dashboards", to: "/dashboards" });
  if (["ho.acc_hq", "ho.cpfc", "ho.pension", "ho.audit"].includes(role)) out.push({ labelKey: "navigation.policy", to: "/policy" });
  if (role === "ho.fa_cao") out.push({ labelKey: "navigation.interest", to: "/finance/interest" });
  if (role === "ho.security") out.push({ labelKey: "navigation.security", to: "/security/activity" }, { labelKey: "navigation.sessions", to: "/security/sessions" });
  if (role === "ho.caiu") out.push({ labelKey: "navigation.riskSignals", to: "/caiu/signals" });
  if (role === "ho.security" || role === "ho.audit") out.push({ labelKey: "navigation.audit", to: "/audit/log" });
  return out;
}

export function menusFor(role: string | undefined): NavGroup[] {
  if (!role) return [];
  if (role === "member") return MEMBER;
  if (role.startsWith("employer.")) return EMPLOYER;
  if (role === "pensioner") return PENSIONER;
  if (role === "claimant") return CLAIMANT;
  if (["fo.apfc_pension", "fo.da_pension", "fo.ss_pension"].includes(role)) return PENSION_OFFICE;
  if (role === "tech.cpps") return [{ label: "CPPS disbursement", to: "/cpps" }];
  if (role.startsWith("fo.")) return fieldOffice(role);
  return poc(role);
}

/** Where "Home" goes for a role. */
export function homeFor(role: string | undefined): string {
  if (role === "member") return "/member/passbook";
  if (role?.startsWith("employer.")) return "/employer";
  if (role === "pensioner") return "/pensioner";
  if (role === "claimant") return "/claimant";
  if (role === "fo.pro_intake") return "/office/pro-counter";
  if (role === "fo.apfc_pension") return "/office/pension-revisions";
  if (role === "fo.da_pension" || role === "fo.ss_pension") return "/office/pension-claims";
  if (role === "tech.cpps") return "/cpps";
  if (role?.startsWith("fo.")) return "/office/work-queue";
  return "/";
}
