import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { api, getSession, rupees } from "../api/client";
import "../i18n";
import { CasePage } from "./office/CasePage";
import type { CaseDetail } from "./office/types";

vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(),
  api: vi.fn(),
  command: vi.fn(),
  getSession: vi.fn(),
}));

afterEach(cleanup);

const renderAt = (path: string, route: string, node: ReactNode) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("P2.28e Officers Case Page UX", () => {
  it("shows the at-a-glance strip with amount, time left, step, form, and advisory marker, with decision section and skip link targeting it when it is the officer's turn", async () => {
    const dueAt = new Date(Date.now() + 3 * 86400000).toISOString();
    const item: CaseDetail = {
      case_id: "CASE-P228E-1",
      claim_id: "CLM-P228E-1",
      grievance_id: null,
      advisory_signal_id: "SIG-ADV-01",
      process: null,
      subject_ref: null,
      kind: "CLAIM",
      office_id: "RO-DELHI-01",
      form_type: "31",
      account_link_id: "AL-1001",
      amount_paise: 5000000,
      rule_version: "illustrative",
      chain: ["fo.da_accounts", "fo.ao", "fo.apfc"],
      step: 1,
      round: 1,
      state: "IN_REVIEW",
      current_role: "fo.ao",
      assignee_subject: null,
      version: 2,
      sla_due_at: dueAt,
      next_action: "decide",
      your_turn: true,
      operation: null,
      history: [],
      docket_ready: true,
    };

    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/office/cases/CASE-P228E-1") return { data: item, meta: {} };
      if (path.includes("/cad")) return { data: { cad_id: "CAD-1", generated_by_role: "fo.ao", gross_paise: 5000000, interest_paise: 0, tds_paise: 0, net_paise: 5000000, tax_basis: "192A", rule_version: "v1", created_at: null }, meta: {} };
      throw new Error(`Unexpected path: ${path}`);
    });
    vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.ao" });

    renderAt("/office/cases/CASE-P228E-1", "/office/cases/:caseId", <CasePage />);

    // Strip is present and displays the key metrics
    const strip = await screen.findByRole("region", { name: "At a glance" });
    expect(strip).toBeTruthy();

    // Strip shows amount
    expect(within(strip).getByText(rupees(item.amount_paise))).toBeTruthy();

    // Strip shows time left ("3 days left")
    expect(within(strip).getByText("3 days left")).toBeTruthy();

    // Strip shows step of the chain ("Step 2 of 3")
    expect(within(strip).getByText("Step 2 of 3")).toBeTruthy();

    // Strip shows form ("Form 31")
    expect(within(strip).getByText("Form 31")).toBeTruthy();

    // Strip shows advisory marker when advisory_signal_id is set
    expect(within(strip).getByText("Advisory")).toBeTruthy();

    // Decision section is present with its existing heading id and text
    const decisionHeading = document.getElementById("case-action-heading");
    expect(decisionHeading).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Decide" })).toBeTruthy();

    // Skip link targets the decision section when it is the officer's turn
    const skipLink = screen.getByRole("link", { name: "Jump to your decision" });
    expect(skipLink).toBeTruthy();
    expect(skipLink.getAttribute("href")).toBe("#case-action-heading");
  });

  it("shows overdue time left using the word 'Overdue' when sla_due_at has passed", async () => {
    const overdueAt = new Date(Date.now() - 2 * 86400000).toISOString();
    const item: CaseDetail = {
      case_id: "CASE-P228E-2",
      claim_id: "CLM-P228E-2",
      grievance_id: null,
      advisory_signal_id: null,
      process: null,
      subject_ref: null,
      kind: "CLAIM",
      office_id: "RO-DELHI-01",
      form_type: "19",
      account_link_id: "AL-1002",
      amount_paise: 12000000,
      rule_version: "illustrative",
      chain: ["fo.da_accounts", "fo.ao"],
      step: 0,
      round: 1,
      state: "IN_REVIEW",
      current_role: "fo.da_accounts",
      assignee_subject: null,
      version: 1,
      sla_due_at: overdueAt,
      next_action: "recommend",
      your_turn: true,
      operation: null,
      history: [],
      docket_ready: true,
    };

    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/office/cases/CASE-P228E-2") return { data: item, meta: {} };
      if (path.includes("/cad")) return { data: { cad_id: "CAD-2", generated_by_role: "fo.da_accounts", gross_paise: 12000000, interest_paise: 0, tds_paise: 0, net_paise: 12000000, tax_basis: "192A", rule_version: "v1", created_at: null }, meta: {} };
      throw new Error(`Unexpected path: ${path}`);
    });
    vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.da_accounts" });

    renderAt("/office/cases/CASE-P228E-2", "/office/cases/:caseId", <CasePage />);

    const strip = await screen.findByRole("region", { name: "At a glance" });
    expect(within(strip).getByText(rupees(item.amount_paise))).toBeTruthy();
    // Time left explicitly contains the word "Overdue" (not just color)
    expect(within(strip).getByText("Overdue by 2 days")).toBeTruthy();
    expect(within(strip).getByText("Step 1 of 2")).toBeTruthy();
    // Advisory marker is absent when advisory_signal_id is null
    expect(within(strip).queryByText("Advisory")).toBeNull();
  });

  it("omits the skip link and decision section when it is not the officer's turn", async () => {
    const item: CaseDetail = {
      case_id: "CASE-P228E-3",
      claim_id: "CLM-P228E-3",
      grievance_id: null,
      advisory_signal_id: null,
      process: null,
      subject_ref: null,
      kind: "CLAIM",
      office_id: "RO-DELHI-01",
      form_type: "31",
      account_link_id: "AL-1003",
      amount_paise: 2500000,
      rule_version: "illustrative",
      chain: ["fo.da_accounts", "fo.ao"],
      step: 1,
      round: 1,
      state: "IN_REVIEW",
      current_role: "fo.ao",
      assignee_subject: null,
      version: 3,
      sla_due_at: null,
      next_action: "decide",
      your_turn: false,
      operation: null,
      history: [],
      docket_ready: true,
    };

    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/office/cases/CASE-P228E-3") return { data: item, meta: {} };
      throw new Error(`Unexpected path: ${path}`);
    });
    vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.da_accounts" });

    renderAt("/office/cases/CASE-P228E-3", "/office/cases/:caseId", <CasePage />);

    const strip = await screen.findByRole("region", { name: "At a glance" });
    expect(within(strip).getByText(rupees(item.amount_paise))).toBeTruthy();
    expect(within(strip).getByText("Step 2 of 2")).toBeTruthy();

    // Skip link is absent
    expect(screen.queryByRole("link", { name: "Jump to your decision" })).toBeNull();

    // Decision section is absent
    expect(document.getElementById("case-action-heading")).toBeNull();
  });
});
