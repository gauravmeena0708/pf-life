import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, getSession } from "../api/client";
import "../i18n";
import { ClaimsPage } from "./member/ClaimsPage";
import { PassbookPage } from "./member/PassbookPage";
import { WorkQueuePage } from "./office/WorkQueuePage";
import type { OfficeCase } from "./office/types";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: vi.fn(),
  command: vi.fn(),
  getSession: vi.fn(),
}));

vi.mock("./stepup/useStepUp", () => ({
  useStepUp: () => ({
    ask: vi.fn(),
    request: null,
    onConfirmed: vi.fn(),
    onCancel: vi.fn(),
  }),
}));

vi.mock("./stepup/StepUpDialog", () => ({
  StepUpDialog: () => null,
}));

afterEach(cleanup);

const wrap = (node: ReactNode, initialEntries = ["/"]) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>
        {node}
      </MemoryRouter>
    </QueryClientProvider>
  );

function verifyResponsiveTable(table: HTMLTableElement) {
  expect(table.classList.contains("responsive-table")).toBe(true);

  const theadThs = Array.from(table.querySelectorAll("thead th"));
  expect(theadThs.length).toBeGreaterThan(0);
  const headers = theadThs.map((th) => th.textContent?.trim() ?? "");
  for (const header of headers) {
    expect(header).toBeTruthy();
  }

  const rows = Array.from(table.querySelectorAll("tbody tr"));
  expect(rows.length).toBeGreaterThan(0);

  for (const row of rows) {
    const tds = Array.from(row.querySelectorAll("td"));
    expect(tds.length).toBe(headers.length);
    tds.forEach((td, colIndex) => {
      const label = td.getAttribute("data-label");
      expect(label).toBeTruthy();
      expect(label?.trim()).toBe(headers[colIndex]);
    });
  }
}

describe("P2.28g phone layouts for wide tables (responsive-table with data-label)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("ClaimsPage: 'Your claims' table has class responsive-table and every cell has non-empty data-label equal to its column header", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/members/me/claims/eligible-types") {
        return {
          data: {
            rule_version: "2026.1",
            illustrative_only: false,
            auto_settlement_limit_paise: 5000000,
            accounts: [
              {
                account_link_id: "AL-0001",
                primary: true,
                balance: { employee_paise: 500000, employer_paise: 500000, total_paise: 1000000 },
                types: [
                  {
                    claim_type: "FINAL_SETTLEMENT",
                    form_type: "19",
                    label: "Final settlement",
                    plain_rule: "Rule 1",
                    eligible: true,
                    max_amount_paise: 1000000,
                    reasons: [],
                  },
                ],
              },
            ],
          },
          meta: {},
        };
      }
      if (path === "/api/v1/members/me/claims") {
        return {
          data: [
            {
              claim_id: "CLM-0001",
              claim_type: "FINAL_SETTLEMENT",
              form_type: "19",
              amount_paise: 500000,
              state: "SUBMITTED",
              next_step: "Pending employer review",
              created_at: "2026-10-01T10:00:00Z",
            },
            {
              claim_id: "CLM-0002",
              claim_type: "PARTIAL_WITHDRAWAL",
              form_type: "31",
              amount_paise: 250000,
              state: "APPROVED",
              next_step: "Payment processing",
              created_at: "2026-10-02T12:00:00Z",
            },
          ],
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/members/me/tax")) {
        return { data: null, meta: {} };
      }
      throw new Error(`Unhandled path: ${path}`);
    });

    wrap(<ClaimsPage />, ["/member/claims"]);

    expect(await screen.findByText("CLM-0001")).toBeTruthy();
    const yourClaimsHeading = screen.getByRole("heading", { name: /Your claims/i });
    const yourClaimsSection = yourClaimsHeading.closest("section");
    expect(yourClaimsSection).toBeTruthy();

    const table = yourClaimsSection!.querySelector("table");
    expect(table).toBeTruthy();
    verifyResponsiveTable(table as HTMLTableElement);
  });

  it("PassbookPage: every entries table has class responsive-table and every cell has non-empty data-label equal to its column header", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/members/me/passbook") {
        return {
          data: {
            accounts: [
              {
                account_link_id: "AL-1001",
                entries: [
                  {
                    wage_month: "2026-08",
                    establishment_name: "Acme Enterprises Ltd",
                    employee_share_paise: 180000,
                    employer_share_paise: 180000,
                    running_balance_paise: 360000,
                    trrn: "TRRN-999888777",
                    posted_at: "2026-09-01T00:00:00Z",
                  },
                  {
                    wage_month: "2026-09",
                    establishment_name: "Acme Enterprises Ltd",
                    employee_share_paise: 180000,
                    employer_share_paise: 180000,
                    running_balance_paise: 540000,
                    trrn: "TRRN-999888778",
                    posted_at: "2026-10-01T00:00:00Z",
                  },
                ],
              },
              {
                account_link_id: "AL-TRUST",
                entries: [],
                trust: {
                  source: "Demo Steel PF Trust",
                  fetched_at: "2026-09-30T10:00:00Z",
                  stale: false,
                  balance: { employee_paise: 120000, employer_paise: 80000 },
                  entries: [
                    { date: "2026-06-30", kind: "CONTRIBUTION", amount_paise: 50000, note: "June contribution" },
                    { date: "2026-07-31", kind: "CONTRIBUTION", amount_paise: 50000, note: "July contribution" },
                  ],
                  service_from: "2020-01-01",
                  service_to: "2026-06-30",
                },
              },
            ],
            pending: [],
          },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/members/me/annual-statements")) {
        return { data: { financial_year: "2026-27", accounts: [], note: "" }, meta: {} };
      }
      if (path.startsWith("/api/v1/members/me/tax")) {
        return {
          data: {
            taxable_interest_paise: 0,
            non_taxable_interest_paise: 0,
            employee_contributions_paise: 0,
            threshold_paise: 0,
            working: "",
            interest_credited: false,
            note: "",
          },
          meta: {},
        };
      }
      throw new Error(`Unhandled path: ${path}`);
    });

    wrap(<PassbookPage />, ["/member/passbook"]);

    expect(await screen.findByText("TRRN-999888777")).toBeTruthy();

    const tables = document.querySelectorAll(".passbook-page section:not([aria-labelledby='annual-statement-heading']) table");
    expect(tables.length).toBe(2);

    for (const table of Array.from(tables)) {
      verifyResponsiveTable(table as HTMLTableElement);
    }
  });

  it("WorkQueuePage: cases table has class responsive-table and every cell has non-empty data-label equal to its column header", async () => {
    const mockCase: OfficeCase = {
      case_id: "CASE-0001",
      claim_id: "CLM-0001",
      grievance_id: null,
      advisory_signal_id: null,
      process: null,
      subject_ref: "MEMBER-0001",
      kind: "claim",
      office_id: "RO-DELHI",
      form_type: "19",
      account_link_id: "AL-0001",
      amount_paise: 500000,
      rule_version: "2026.1",
      chain: ["fo.da_accounts", "fo.ss"],
      step: 0,
      round: 1,
      state: "ASSIGNED",
      current_role: "fo.da_accounts",
      assignee_subject: "officer-1",
      version: 1,
      sla_due_at: "2026-10-14T10:00:00Z",
      next_action: "recommend",
    };

    vi.mocked(getSession).mockResolvedValue({
      authenticated: true,
      subject: "officer.da",
      stakeholder: "fo.da_accounts",
    });

    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/office/work-queue") {
        return {
          data: {
            office_id: "RO-DELHI",
            role: "fo.da_accounts",
            items: [mockCase],
          },
          meta: { correlation_id: "c1", as_of: "2026-10-04" },
        };
      }
      if (path === "/api/v1/office/stopped-cases") {
        return { data: [], meta: { correlation_id: "c2", as_of: "2026-10-04" } };
      }
      throw new Error(`Unhandled path: ${path}`);
    });

    wrap(<WorkQueuePage />, ["/office/work-queue"]);

    expect(await screen.findByText("CASE-0001")).toBeTruthy();

    const table = screen.getByRole("table");
    verifyResponsiveTable(table as HTMLTableElement);
  });
});
