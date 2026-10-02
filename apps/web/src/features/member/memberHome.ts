import { rupees } from "../../api/client";
import type { TFunction } from "i18next";
import i18n from "../../i18n";
import { statusLabel } from "../statusLabel";

export interface MemberHomeInput {
  profile?: { name: string; uan: string; kyc: { aadhaar: string; pan: string; bank: string }; international_worker?: boolean };
  service?: { member_ids: { account_link_id: string; establishment_name: string; date_of_joining: string; date_of_exit: string | null;
    last_contribution_month: string | null; transferred_to: string | null; status: string; mark_exit_allowed: boolean; primary?: boolean }[]; total_service_months: number };
  eligibility?: { accounts: { account_link_id: string; primary?: boolean; balance: { total_paise: number };
    types: { claim_type: string; label: string; eligible?: boolean; max_amount_paise?: number }[] }[] };
  claims?: { claim_id: string; claim_type: string; form_type: string; amount_paise: number; state: string; next_step: string; created_at: string }[];
  applications?: { application_id: string; title: string; state: string; pending: boolean; updated_at: string }[];
  nominations?: { current: { state: string } | null };
  pension?: { scenarios: { label: string; eligible: boolean; monthly_paise: number }[]; note: string; age_years?: number };
  pensionApplications?: { claim_id: string; state: string }[];
  passbook?: { pending: { message: string }[] };
}

export interface Nudge { id: string; titleKey: string; titleValues?: Record<string, string | number>;
  detailKey: string; detailValues?: Record<string, string | number>; to: string; tone: "action" | "info" }
export interface PendingItem { id: string; title: string; next: string; to: string }

export function balances(input: MemberHomeInput) {
  const byId = new Map(input.eligibility?.accounts.map((account) => [account.account_link_id, account.balance.total_paise]) ?? []);
  const accounts = input.service?.member_ids.map((row) => ({ ...row,
    primary: row.primary ?? input.eligibility?.accounts.find((account) => account.account_link_id === row.account_link_id)?.primary ?? false,
    balance_paise: byId.get(row.account_link_id) ?? 0 })) ?? [];
  return { total_paise: input.eligibility?.accounts.reduce((sum, account) => sum + account.balance.total_paise, 0) ?? 0, accounts };
}

export function nudges(input: MemberHomeInput, today: Date): Nudge[] {
  const actions: Nudge[] = [];
  const { accounts } = balances(input);
  for (const row of accounts) {
    if (row.date_of_exit && !row.transferred_to && !row.primary && row.balance_paise > 0) actions.push({
      id: `old-id-balance:${row.account_link_id}`, titleKey: "memberHome.nudges.transferTitle",
      titleValues: { amount: rupees(row.balance_paise), establishment: row.establishment_name },
      detailKey: "memberHome.nudges.transferDetail", detailValues: { memberId: row.account_link_id },
      to: "/member/service#transfer-heading", tone: "action" });
  }
  const missing = input.profile && (["aadhaar", "pan", "bank"] as const).filter((key) => input.profile?.kyc[key] !== "VERIFIED");
  if (missing?.length) actions.push({ id: "kyc", titleKey: "memberHome.nudges.kycTitle",
    titleValues: { fields: missing.map((key) => key === "pan" ? "PAN" : key === "aadhaar" ? "Aadhaar" : "bank").join(", ") },
    detailKey: "memberHome.nudges.kycDetail", to: "/member/kyc", tone: "action" });
  if (input.nominations && input.nominations.current?.state !== "CURRENT") actions.push({ id: "nomination", titleKey: "memberHome.nudges.nominationTitle",
    detailKey: "memberHome.nudges.nominationDetail", to: "/member/nomination#nomination-heading", tone: "action" });
  const cutoffMonth = new Date(Date.UTC(today.getFullYear(), today.getMonth() - 2, 1)).toISOString().slice(0, 7);
  for (const row of accounts) {
    if (!row.date_of_exit && row.mark_exit_allowed && row.last_contribution_month && row.last_contribution_month <= cutoffMonth
      && accounts.some((other) => other.account_link_id !== row.account_link_id && other.date_of_joining > row.date_of_joining)) actions.push({
      id: `exit-not-marked:${row.account_link_id}`, titleKey: "memberHome.nudges.exitTitle",
      titleValues: { establishment: row.establishment_name }, detailKey: "memberHome.nudges.exitDetail",
      detailValues: { memberId: row.account_link_id, month: row.last_contribution_month },
      to: "/member/service#exit-heading", tone: "action" });
  }
  // P2.21: what the member may claim now, offered with the amount filled in — one step to confirm
  const open = new Set((input.claims ?? []).filter((c) => !["SETTLED", "REJECTED_WITH_REASON", "REJECTED_BY_EMPLOYER", "CANCELLED"].includes(c.state))
    .map((c) => c.claim_type));
  for (const account of input.eligibility?.accounts ?? []) {
    for (const type of account.types) {
      if (["FINAL_SETTLEMENT", "PENSION_WITHDRAWAL"].includes(type.claim_type) && type.eligible && (type.max_amount_paise ?? 0) > 0 && !open.has(type.claim_type)) {
        actions.push({ id: `ready:${account.account_link_id}:${type.claim_type}`, titleKey: "memberHome.nudges.readyTitle",
          titleValues: { label: type.label, amount: rupees(type.max_amount_paise!) }, detailKey: "memberHome.nudges.readyDetail",
          detailValues: { memberId: account.account_link_id }, tone: "action",
          to: `/member/claims?account=${encodeURIComponent(account.account_link_id)}&type=${type.claim_type}&amount=${Math.floor(type.max_amount_paise! / 100)}` });
      }
    }
  }
  const inService = (input.service?.member_ids ?? []).some((row) => !row.date_of_exit);
  const due = input.pension?.scenarios[0];
  if (input.pension && (input.pension.age_years ?? 0) >= 58 && due?.eligible && !inService && input.pensionApplications && !input.pensionApplications.length) {
    actions.push({ id: "pension-due", titleKey: "memberHome.nudges.pensionDueTitle", titleValues: { amount: rupees(due.monthly_paise) },
      detailKey: "memberHome.nudges.pensionDueDetail", to: "/member/pension#form10d-heading", tone: "action" });
  }
  const count = input.passbook?.pending.length ?? 0;
  if (count) actions.push({ id: "passbook-pending", titleKey: "memberHome.nudges.passbookTitle",
    titleValues: { count }, detailKey: "memberHome.nudges.passbookDetail", detailValues: { message: input.passbook!.pending[0].message },
    to: "/member/passbook", tone: "info" });
  return actions;
}

export function pendingItems(input: MemberHomeInput, t: TFunction = i18n.t): PendingItem[] {
  const final = new Set(["SETTLED", "REJECTED_WITH_REASON", "REJECTED_BY_EMPLOYER", "CANCELLED"]);
  return [
    ...(input.claims ?? []).filter((claim) => !final.has(claim.state)).map((claim) => ({
      id: `claim:${claim.claim_id}`, title: input.eligibility?.accounts.flatMap((account) => account.types)
        .find((type) => type.claim_type === claim.claim_type)?.label ?? `Form ${claim.form_type}`,
      next: claim.next_step, to: `/member/claims/${encodeURIComponent(claim.claim_id)}` })),
    ...(input.applications ?? []).filter((app) => app.pending).map((app) => ({ id: `application:${app.application_id}`,
      title: app.title, next: statusLabel(app.state, t), to: "/member/service#applications-heading" })),
  ];
}
