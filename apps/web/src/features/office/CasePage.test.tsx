import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { api, getSession } from "../../api/client";
import "../../i18n";
import { CasePage } from "./CasePage";
import type { CaseDetail } from "./types";

vi.mock("../../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../api/client")>(),
  api: vi.fn(), getSession: vi.fn(),
}));

afterEach(cleanup);

it("keeps the returned case visible when an officer decision has no scrutiny checks", async () => {
  const reason = "Please supply supporting evidence.";
  const item: CaseDetail = {
    case_id: "CASE-UI", claim_id: "CLM-UI", grievance_id: null, advisory_signal_id: null,
    process: null, subject_ref: null, kind: "CLAIM", office_id: "RO-01", form_type: "31",
    account_link_id: "AL-01", amount_paise: 10000100, rule_version: "illustrative",
    chain: ["fo.da_accounts", "fo.ao"], step: 0, round: 2, state: "IN_REVIEW",
    current_role: "fo.da_accounts", assignee_subject: null, version: 4, sla_due_at: null,
    next_action: "recommend", your_turn: false, operation: null,
    history: [
      { at: "2026-09-30T10:00:00Z", round: 1, officer_role: "fo.da_accounts", officer_subject: "initiator",
        action: "RECOMMEND", approval_level: null, reason: "Checked", checks: ["KYC verified"] },
      { at: "2026-09-30T10:01:00Z", round: 1, officer_role: "fo.ao", officer_subject: "reviewer",
        action: "RETURN", approval_level: "1", reason, checks: null },
    ],
  };
  vi.mocked(api).mockResolvedValue({ data: item, meta: { correlation_id: "ui-test", as_of: "2026-09-30" } });
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.ao" });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/office/cases/CASE-UI"]}>
    <Routes><Route path="/office/cases/:caseId" element={<CasePage />} /></Routes>
  </MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText(reason)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Case details" })).toBeTruthy();
  expect(screen.getByText("Checked; KYC verified")).toBeTruthy();
  client.clear();
});
