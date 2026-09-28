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
    link("Profile", "/member/profile#member-profile-heading"), link("Service History", "/member/profile#employment-heading"),
    link("UAN Card"), link("Passbook", "/member/passbook"), link("Pension estimate", "/member/profile#pension-estimate-heading")] },
  { label: "Manage", items: [
    link("Basic Details (Joint Declaration)", "/member/profile#correction-heading"), link("Contact Details", "/member/security#contact-heading"),
    link("KYC", "/member/profile#assurance-heading"), link("E-Nomination"), link("Mark Exit")] },
  { label: "Account", items: [link("Change Password"), { labelKey: "navigation.accountSecurity", to: "/member/security" }] },
  { label: "Online Services", items: [
    link("Claim (Form-31, 19, 10C & 10D)", "/member/claims"), link("One Member – One EPF Account (Transfer Request)"),
    link("Track Claim Status", "/member/claims"), link("Download Annexure K"), link("Joint Declaration", "/member/profile#correction-heading"),
    link("Form 15G / 15H", "/member/claims#tax-declaration-heading")] },
  { label: "PMVBRY" },
  { labelKey: "navigation.help", items: [{ labelKey: "navigation.grievances", to: "/member/grievances" }, { labelKey: "navigation.assistant", to: "/member/assistant" }] },
];

const EMPLOYER: NavGroup[] = [
  { label: "Member", items: [
    link("Register-Individual"), link("Register-Bulk"), link("Member Profile"), link("Approvals"),
    link("Approve KYC pending for Digital Signature"), link("Approve KYC seeded by member"), link("KYC Bulk"), link("Exit-Bulk"),
    link("Missing details"), link("Member Location Mapping"), link("KYC Verification / PAN Verification"),
    link("Joint Declaration requests", "/employer#jd-heading")] },
  { label: "Establishment", items: [
    link("Establishment Profile", "/employer#emp-heading"), link("Form 5A"), link("Branches (Form 2A)"),
    link("DSC/e-sign Registration"), link("e-sign Registration"), link("Authorized eSign List", "/employer#people-signatory")] },
  { label: "Payments", items: [
    link("ECR Upload", "/employer/ecr#ecr-prepare"), link("Return Filing", "/employer/ecr#ecr-returns"), link("Return monthly dashboard"),
    link("Direct Challan"), link("Monthly Return for Exempted Establishment"), link("TRRN query / challan status", "/employer/ecr#ecr-challans")] },
  { label: "Dashboards", items: [link("Active Members details"), link("Missing details")] },
  { label: "User", items: [link("Sub-users (payroll operators)", "/employer#people-operator")] },
  { label: "Admin" },
  { label: "Online Services", items: [link("Transfer Claims"), link("Claim attestation"), link("Higher-pension joint-option validation")] },
  { label: "PMVBRY" },
  { label: "EEC-2026/VISHWAS" },
];

/** Field Office Interface: the top-level menus seen on live screens, grouped (the real bar wraps onto 2–3 rows). */
function fieldOffice(role: string): NavGroup[] {
  const queue = "/office/work-queue";
  return [
    { label: "Claims & settlement", items: [link("CLAIMS", queue), link("Online Services", queue), link("ANNEXURE K FILE")] },
    { label: "Members", items: [link("Member", role === "fo.oic" ? queue : undefined), link("Query")] },
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
  { label: "Pension", items: [link("Pension revisions", "/office/pension-revisions"), link("Pension Enquiry Details"), link("Track Pension Claims Updation Activities")] },
  { label: "CLAIMS" },
];

/** Pensioners' portal: public enquiries (no pensioner login exists; the POC adds one for the pension view). */
const PENSIONER: NavGroup[] = [
  { labelKey: "navigation.pension", to: "/pensioner" },
  { label: "Pensioners' Portal", items: [
    link("Jeevan Pramaan Enquiry"), link("Know your PPO No."), link("PPO Enquiry / Payment Enquiry", "/pensioner#pension-payments-heading"),
    link("Know Your Pension Status", "/pensioner#monthly-pension-heading"), link("Know Your Pension Payee Bank")] },
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
  if (role === "fo.apfc_pension" || role === "fo.da_pension") return PENSION_OFFICE;
  if (role.startsWith("fo.")) return fieldOffice(role);
  return poc(role);
}

/** Where "Home" goes for a role. */
export function homeFor(role: string | undefined): string {
  if (role === "member") return "/member/passbook";
  if (role?.startsWith("employer.")) return "/employer";
  if (role === "pensioner") return "/pensioner";
  if (role === "fo.apfc_pension") return "/office/pension-revisions";
  if (role?.startsWith("fo.")) return "/office/work-queue";
  return "/";
}
