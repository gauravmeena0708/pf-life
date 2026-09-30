import { describe, expect, it } from "vitest";

import { balances, nudges, pendingItems, type MemberHomeInput } from "./memberHome";

const old = { account_link_id: "OLD", establishment_name: "Old Works", date_of_joining: "2018-01-01", date_of_exit: "2023-01-31",
  last_contribution_month: "2022-12", transferred_to: null, status: "EXITED", mark_exit_allowed: false, primary: false };
const current = { ...old, account_link_id: "NEW", establishment_name: "New Works", date_of_joining: "2024-01-01", date_of_exit: null,
  last_contribution_month: "2026-08", status: "ACTIVE", primary: true };
const input: MemberHomeInput = {
  profile: { name: "Demo Member", uan: "1001", kyc: { aadhaar: "VERIFIED", pan: "VERIFIED", bank: "VERIFIED" } },
  service: { member_ids: [old, current], total_service_months: 96 },
  eligibility: { accounts: [
    { account_link_id: "OLD", balance: { total_paise: 120050 }, types: [{ claim_type: "ADVANCE", label: "Medical advance" }] },
    { account_link_id: "NEW", primary: true, balance: { total_paise: 300000 }, types: [] },
  ] },
  nominations: { current: { state: "CURRENT" } }, passbook: { pending: [] },
};
const today = new Date("2026-09-30T12:00:00Z");
const withInput = (change: Partial<MemberHomeInput>): MemberHomeInput => ({ ...input, ...change });

describe("balances", () => {
  it("joins balances by member ID and totals all eligible accounts", () => {
    expect(balances(input)).toMatchObject({ total_paise: 420050, accounts: [
      { account_link_id: "OLD", balance_paise: 120050, primary: false },
      { account_link_id: "NEW", balance_paise: 300000, primary: true },
    ] });
  });
});

describe("nudges", () => {
  it("prompts transfer only for a non-primary exited account with balance", () => {
    expect(nudges(input, today).find((item) => item.id.startsWith("old-id-balance"))).toMatchObject({
      title: "Move ₹1,200.50 from Old Works to your current account", to: "/member/service#transfer-heading" });
    for (const change of [{ date_of_exit: null }, { transferred_to: "NEW" }, { primary: true }]) {
      expect(nudges(withInput({ service: { ...input.service!, member_ids: [{ ...old, ...change }, current] } }), today).some((item) => item.id.startsWith("old-id-balance"))).toBe(false);
    }
    expect(nudges(withInput({ eligibility: { accounts: [{ ...input.eligibility!.accounts[0], balance: { total_paise: 0 } }] } }), today)
      .some((item) => item.id.startsWith("old-id-balance"))).toBe(false);
  });

  it("prompts KYC only for unverified fields", () => {
    expect(nudges(input, today).some((item) => item.id === "kyc")).toBe(false);
    expect(nudges(withInput({ profile: { ...input.profile!, kyc: { aadhaar: "PENDING", pan: "VERIFIED", bank: "NOT_VERIFIED" } } }), today)
      .find((item) => item.id === "kyc")?.title).toBe("Complete your KYC (Aadhaar, bank)");
  });

  it("prompts nomination for absent or inactive records", () => {
    expect(nudges(input, today).some((item) => item.id === "nomination")).toBe(false);
    expect(nudges(withInput({ nominations: { current: null } }), today).find((item) => item.id === "nomination")?.to)
      .toBe("/member/nomination#nomination-heading");
    expect(nudges(withInput({ nominations: { current: { state: "SUPERSEDED" } } }), today).some((item) => item.id === "nomination")).toBe(true);
  });

  it("prompts exit only when a later job exists and two full months have passed", () => {
    const stale = { ...old, date_of_exit: null, mark_exit_allowed: true };
    expect(nudges(withInput({ service: { ...input.service!, member_ids: [stale, current] } }), today)
      .find((item) => item.id.startsWith("exit-not-marked"))?.to).toBe("/member/service#exit-heading");
    for (const change of [{ mark_exit_allowed: false }, { last_contribution_month: "2026-08" }, { date_of_exit: "2023-01-31" }]) {
      expect(nudges(withInput({ service: { ...input.service!, member_ids: [{ ...stale, ...change }, current] } }), today)
        .some((item) => item.id.startsWith("exit-not-marked"))).toBe(false);
    }
    expect(nudges(withInput({ service: { ...input.service!, member_ids: [stale] } }), today)
      .some((item) => item.id.startsWith("exit-not-marked"))).toBe(false);
  });

  it("shows pending passbook entries after actions and omits the notice when clear", () => {
    expect(nudges(input, today).some((item) => item.id === "passbook-pending")).toBe(false);
    const result = nudges(withInput({ passbook: { pending: [{ message: "Awaiting posting" }] } }), today);
    expect(result.at(-1)).toMatchObject({ id: "passbook-pending", tone: "info", title: "1 contribution(s) not yet in your passbook" });
  });
});

describe("pendingItems", () => {
  it("uses claim labels and next steps, excludes final claims, and includes pending applications", () => {
    const claims = ["SUBMITTED", "SETTLED", "REJECTED_WITH_REASON", "REJECTED_BY_EMPLOYER", "CANCELLED"].map((state, index) => ({
      claim_id: `C${index}`, claim_type: "ADVANCE", form_type: "31", amount_paise: 100, state, next_step: "Employer attestation needed", created_at: "2026-09-01" }));
    expect(pendingItems(withInput({ claims, applications: [
      { application_id: "A1", title: "Transfer request", state: "PENDING_EMPLOYER", pending: true, updated_at: "2026-09-01" },
      { application_id: "A2", title: "Processed", state: "APPROVED", pending: false, updated_at: "2026-09-01" },
    ] }))).toEqual([
      { id: "claim:C0", title: "Medical advance", next: "Employer attestation needed", to: "/member/claims/C0" },
      { id: "application:A1", title: "Transfer request", next: "pending employer", to: "/member/service#applications-heading" },
    ]);
    expect(pendingItems(withInput({ eligibility: undefined, claims: [claims[0]] }))[0].title).toBe("Form 31");
  });
});
