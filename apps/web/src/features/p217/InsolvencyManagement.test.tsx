import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, command } from "../../api/client";
import {
  InsolvencyManagementPage,
  type InsolvencyCase,
  type OfficeSummary,
  type WatchlistResponse,
} from "./InsolvencyManagement";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  api: vi.fn(),
  command: vi.fn(),
}));

afterEach(cleanup);

function renderPage(page: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>
  );
}

const mockWatchlist: WatchlistResponse = {
  as_of: "2026-10-05",
  office_id: "RO-DEMO-01",
  total_flagged: 2,
  watchlist: [
    {
      establishment_id: "EST-DEMO-0002",
      legal_name: "Demo Engineering Works",
      score: 65,
      risk_level: "HIGH",
      reasons: [
        "ECR filing stopped for 4 months after regular filing (last return filed: 2026-02)",
        "Open demands in default (1 demand(s), ₹30,000)",
      ],
      signals: {
        ecr_stopped: true,
        last_ecr_month: "2026-02",
        months_unfiled: 4,
        open_demands_count: 1,
        open_demands_paise: 3000000,
        mca_status: null,
      },
    },
    {
      establishment_id: "EST-DEMO-0003",
      legal_name: "Demo Retail Cooperative",
      score: 50,
      risk_level: "MEDIUM",
      reasons: ["MCA status: UNDER_CIRP"],
      signals: {
        ecr_stopped: false,
        last_ecr_month: null,
        months_unfiled: 0,
        open_demands_count: 0,
        open_demands_paise: 0,
        mca_status: "UNDER_CIRP",
      },
    },
  ],
};

const mockCases: InsolvencyCase[] = [
  {
    case_id: "INS-TEST-01",
    establishment_id: "EST-DEMO-0002",
    legal_name: "Demo Engineering Works",
    office_id: "RO-DEMO-01",
    stage: "CIRP",
    practitioner_type: "IRP",
    practitioner_name: "Shri V. Sharma, IP",
    announcement_date: "2026-10-01",
    claim_deadline: "2026-10-15",
    claim_period_days: 14,
    claim_filed: false,
    claimed_principal_paise: 0,
    claimed_damages_paise: 0,
    claimed_interest_paise: 0,
    total_claimed_paise: 0,
    moratorium_active: true,
    outside_liquidation_estate: false,
    realised_paise: 0,
    recovery_pct: 0,
    outstanding_paise: 0,
    state: "OPEN",
    warning: "Urgent: Claim submission deadline is in 2 day(s) on 2026-10-15. Claim not yet filed!",
    warning_code: "CLAIM_DEADLINE_APPROACHING",
    days_to_deadline: 2,
    created_at: "2026-10-01T10:00:00Z",
  },
];

const mockSummary: OfficeSummary = {
  as_of: "2026-10-05",
  office_id: "RO-DEMO-01",
  total_cases: 3,
  by_stage: { CIRP: 2, LIQUIDATION: 1 },
  by_state: { OPEN: 1, CLAIM_FILED: 1, CLOSED: 1 },
  claims_pending: 1,
  claims_filed: 2,
  claims_due_soon: 1,
  total_claimed_paise: 7500000,
  total_recovered_paise: 3000000,
  overall_recovery_pct: 40.0,
  resolution_plans: {
    compliant: 1,
    non_compliant: 0,
    total: 1,
  },
  moratorium_active_cases: 2,
};

describe("InsolvencyManagementPage (P2.17)", () => {
  beforeEach(() => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.includes("/watchlist")) return { data: mockWatchlist, meta: { correlation_id: "c1", as_of: "2026-10-05" } };
      if (path.includes("/summary")) return { data: mockSummary, meta: { correlation_id: "c2", as_of: "2026-10-05" } };
      if (path.includes("/insolvency-cases/INS-TEST-01/dues-summary")) {
        return {
          data: {
            case_id: "INS-TEST-01",
            establishment_id: "EST-DEMO-0002",
            principal_paise: 3000000,
            damages_paise: 300000,
            interest_paise: 150000,
            total_dues_paise: 3450000,
            demands: [],
          },
          meta: { correlation_id: "c3", as_of: "2026-10-05" },
        };
      }
      if (path.includes("/insolvency-cases/INS-TEST-01")) return { data: mockCases[0], meta: { correlation_id: "c4", as_of: "2026-10-05" } };
      if (path.includes("/insolvency-cases")) return { data: mockCases, meta: { correlation_id: "c5", as_of: "2026-10-05" } };
      return { data: null, meta: { correlation_id: "c0", as_of: "2026-10-05" } };
    });
  });

  it("renders watchlist with scored establishments and reasons", async () => {
    renderPage(<InsolvencyManagementPage />);

    expect(screen.getByText("Insolvency & Bankruptcy (IBC) Proceedings")).toBeTruthy();
    expect(screen.getByText(/Section 14/)).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText("Demo Engineering Works")).toBeTruthy();
    });
    expect(screen.getByText(/High Risk/)).toBeTruthy();
    expect(screen.getByText(/ECR filing stopped for 4 months/)).toBeTruthy();
    expect(screen.getByText("Demo Retail Cooperative")).toBeTruthy();
    expect(screen.getByText(/MCA status: UNDER_CIRP/)).toBeTruthy();
  });

  it("switches to cases tab and displays cases with deadline warnings", async () => {
    renderPage(<InsolvencyManagementPage />);

    fireEvent.click(screen.getByText("Insolvency Cases"));

    await waitFor(() => {
      expect(screen.getByText("INS-TEST-01")).toBeTruthy();
    });
    expect(screen.getByText(/Urgent: Claim submission deadline is in 2 day/)).toBeTruthy();
  });

  it("records an IBBI announcement via form submission", async () => {
    vi.mocked(command).mockResolvedValueOnce({
      data: {
        case_id: "INS-NEW-01",
        establishment_id: "EST-DEMO-0002",
        stage: "CIRP",
        claim_deadline: "2026-10-15",
        moratorium_active: true,
      },
      meta: { correlation_id: "c6", as_of: "2026-10-05" },
    });

    renderPage(<InsolvencyManagementPage />);
    fireEvent.click(screen.getByText("Insolvency Cases"));

    const submitBtn = screen.getByRole("button", { name: "Record Announcement & Compute Deadline" });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(command).toHaveBeenCalledWith(
        "POST",
        "/api/v1/office/compliance/insolvency-cases",
        expect.objectContaining({
          establishment_id: "EST-DEMO-0002",
          stage: "CIRP",
          claim_period_days: 14,
        })
      );
    });
  });

  it("switches to summary tab and displays office insolvency metrics", async () => {
    renderPage(<InsolvencyManagementPage />);

    fireEvent.click(screen.getByText("Office Summary"));

    await waitFor(() => {
      expect(screen.getByText("Insolvency Recovery & Compliance Summary")).toBeTruthy();
    });
    expect(screen.getByText("3")).toBeTruthy(); // total cases
    expect(screen.getByText("40%")).toBeTruthy(); // overall recovery
  });
});
