import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api, getSession } from "../api/client";
import "../i18n";
import { ClaimDetailPage } from "./member/ClaimDetailPage";
import { CasePage } from "./office/CasePage";
import type { CaseDetail } from "./office/types";
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
afterEach(cleanup);

const at = (path: string, route: string, node: ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
  <MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={node} /></Routes></MemoryRouter></QueryClientProvider>);

it("tells the member what fixes a rejected claim, with the way there (P2.23b)", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/members/me/claims/CLM-R") return { data: { claim_id: "CLM-R", account_link_id: "AL-0001", claim_type: "ADVANCE_ILLNESS", form_type: "31",
      amount_paise: 100000, state: "REJECTED_WITH_REASON", version: 5, rule_version: "demo", summary: "Advance", payment_id: null, next_step: "",
      decision_reason: "The bank account does not match the records. The account is not the member's", timeline: [],
      decision_fix: { code: "BANK_DETAILS", label: "The bank account does not match the records", fix: "Seed your correct bank account under KYC.", link: "/member/kyc" } }, meta: {} };
    throw new Error("not available");
  });
  at("/member/claims/CLM-R", "/member/claims/:claimId", <ClaimDetailPage />);
  expect(await screen.findByText(/Seed your correct bank account under KYC/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Go there" }).getAttribute("href")).toBe("/member/kyc");
});

it("asks the officer recommending rejection for the reason, and shows what the member will read (P2.23b)", async () => {
  const item: CaseDetail = {
    case_id: "CASE-R", claim_id: "CLM-R", grievance_id: null, advisory_signal_id: null, process: null, subject_ref: null, kind: "CLAIM",
    office_id: "RO-DEMO-01", form_type: "31", account_link_id: "AL-0001", amount_paise: 100000, rule_version: "demo",
    chain: ["fo.da_accounts", "fo.ao"], step: 0, round: 1, state: "IN_REVIEW", current_role: "fo.da_accounts", assignee_subject: null,
    version: 1, sla_due_at: null, next_action: "recommend", your_turn: true, operation: null, history: [], docket_ready: true,
    rejection_reasons: [{ code: "BANK_DETAILS", label: "The bank account does not match the records", fix: "Seed your correct bank account under KYC." },
      { code: "OTHER", label: "Other", fix: "The officer's note says what to do." }],
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/office/cases/CASE-R") return { data: item, meta: {} };
    throw new Error("not available");
  });
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.da_accounts" });
  at("/office/cases/CASE-R", "/office/cases/:caseId", <CasePage />);
  fireEvent.click(await screen.findByLabelText("Recommend to Reject"));
  const select = screen.getByLabelText(/Reason for rejection/);
  fireEvent.change(select, { target: { value: "BANK_DETAILS" } });
  expect(screen.getByText("The member will read: Seed your correct bank account under KYC.")).toBeTruthy();
});
