import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, afterEach } from "vitest";

import { api, getSession } from "../api/client";
import "../i18n";
import {
  filterCases,
  getCaseCategory,
  getQueueCounts,
  sortCases,
  timeLeft,
} from "./office/queue";
import type { OfficeCase } from "./office/types";
import { WorkQueuePage } from "./office/WorkQueuePage";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: vi.fn(),
  getSession: vi.fn(),
}));

afterEach(cleanup);

const wrap = (node: ReactNode, initialEntries = ["/office/work-queue"]) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/office/work-queue" element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

function createMockCase(index: number, overrides: Partial<OfficeCase> = {}): OfficeCase {
  const num = String(index).padStart(4, "0");
  return {
    case_id: `CASE-${num}`,
    claim_id: `CLM-${num}`,
    grievance_id: null,
    advisory_signal_id: null,
    process: null,
    subject_ref: `MEMBER-${num}`,
    kind: "claim",
    office_id: "RO-DELHI",
    form_type: "19",
    account_link_id: `AL-${num}`,
    amount_paise: 100000 + index * 5000,
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
    ...overrides,
  };
}

describe("P2.28d queue logic: timeLeft, sortCases, filterCases", () => {
  const refNow = new Date("2026-10-04T10:00:00Z");

  describe("timeLeft wording incl. overdue/today", () => {
    it("formats future dates as 'X days left'", () => {
      expect(timeLeft("2026-10-07T10:00:00Z", refNow).text).toBe("3 days left");
      expect(timeLeft("2026-10-05T10:00:00Z", refNow).text).toBe("1 day left");
      expect(timeLeft("2026-10-07T10:00:00Z", refNow).overdue).toBe(false);
      expect(timeLeft("2026-10-07T10:00:00Z", refNow).dueToday).toBe(false);
    });

    it("formats today's deadlines as 'Due today'", () => {
      expect(timeLeft("2026-10-04T18:00:00Z", refNow).text).toBe("Due today");
      expect(timeLeft("2026-10-04T02:00:00Z", refNow).text).toBe("Due today");
      expect(timeLeft("2026-10-04T10:00:00Z", refNow).overdue).toBe(false);
      expect(timeLeft("2026-10-04T10:00:00Z", refNow).dueToday).toBe(true);
    });

    it("formats past deadlines as 'Overdue by X days'", () => {
      expect(timeLeft("2026-10-03T10:00:00Z", refNow).text).toBe("Overdue by 1 day");
      expect(timeLeft("2026-10-02T10:00:00Z", refNow).text).toBe("Overdue by 2 days");
      expect(timeLeft("2026-10-02T10:00:00Z", refNow).overdue).toBe(true);
      expect(timeLeft("2026-10-02T10:00:00Z", refNow).dueToday).toBe(false);
    });

    it("handles missing or invalid dates gracefully", () => {
      expect(timeLeft(null, refNow).text).toBe("—");
      expect(timeLeft(undefined, refNow).text).toBe("—");
      expect(timeLeft("invalid-date", refNow).text).toBe("—");
      expect(timeLeft(null, refNow).overdue).toBe(false);
    });

    it("supports String coercion", () => {
      expect(String(timeLeft("2026-10-07T10:00:00Z", refNow))).toBe("3 days left");
      expect(String(timeLeft("2026-10-04T10:00:00Z", refNow))).toBe("Due today");
      expect(String(timeLeft("2026-10-02T10:00:00Z", refNow))).toBe("Overdue by 2 days");
    });
  });

  describe("sortCases", () => {
    const caseOverdue = createMockCase(1, { sla_due_at: "2026-10-02T10:00:00Z", amount_paise: 200000 });
    const caseToday = createMockCase(2, { sla_due_at: "2026-10-04T10:00:00Z", amount_paise: 500000 });
    const caseFuture = createMockCase(3, { sla_due_at: "2026-10-07T10:00:00Z", amount_paise: 100000 });
    const caseNoDeadline = createMockCase(4, { sla_due_at: null, amount_paise: 300000 });

    it("sorts by deadline soonest first by default", () => {
      const sorted = sortCases([caseFuture, caseNoDeadline, caseToday, caseOverdue], "deadline");
      expect(sorted.map((c) => c.case_id)).toEqual(["CASE-0001", "CASE-0002", "CASE-0003", "CASE-0004"]);
    });

    it("sorts by amount high to low", () => {
      const sorted = sortCases([caseOverdue, caseFuture, caseToday, caseNoDeadline], "amount");
      expect(sorted.map((c) => c.case_id)).toEqual(["CASE-0002", "CASE-0004", "CASE-0001", "CASE-0003"]);
    });

    it("sorts by oldest first", () => {
      const cA = { ...createMockCase(1), created_at: "2026-09-01T00:00:00Z" } as OfficeCase;
      const cB = { ...createMockCase(2), created_at: "2026-09-15T00:00:00Z" } as OfficeCase;
      const cC = { ...createMockCase(3), created_at: "2026-08-20T00:00:00Z" } as OfficeCase;
      const sorted = sortCases([cB, cA, cC], "oldest");
      expect(sorted.map((c) => c.case_id)).toEqual(["CASE-0003", "CASE-0001", "CASE-0002"]);
    });
  });

  describe("filterCases and getCaseCategory", () => {
    const claimCase = createMockCase(1, { case_id: "CASE-CLAIM", claim_id: "CLM-999", subject_ref: "SUB-1" });
    const grievanceCase = createMockCase(2, {
      case_id: "CASE-GRIEV",
      claim_id: null,
      grievance_id: "GRV-555",
      kind: "grievance",
      subject_ref: "SUB-2",
    });
    const processCase = createMockCase(3, {
      case_id: "CASE-PROC",
      claim_id: null,
      process: "7a_inquiry",
      kind: "process",
      subject_ref: "SUB-3",
    });

    it("correctly identifies case categories", () => {
      expect(getCaseCategory(claimCase)).toBe("claims");
      expect(getCaseCategory(grievanceCase)).toBe("grievances");
      expect(getCaseCategory(processCase)).toBe("other");
    });

    it("filters by text search across case_id, claim_id, grievance_id, and subject_ref", () => {
      expect(filterCases([claimCase, grievanceCase, processCase], { search: "CASE-CLAIM" })).toEqual([claimCase]);
      expect(filterCases([claimCase, grievanceCase, processCase], { search: "GRV-555" })).toEqual([grievanceCase]);
      expect(filterCases([claimCase, grievanceCase, processCase], { search: "SUB-3" })).toEqual([processCase]);
      expect(filterCases([claimCase, grievanceCase, processCase], { search: "non-existent" })).toEqual([]);
    });

    it("filters by kind category", () => {
      expect(filterCases([claimCase, grievanceCase, processCase], { kind: "claims" })).toEqual([claimCase]);
      expect(filterCases([claimCase, grievanceCase, processCase], { kind: "grievances" })).toEqual([grievanceCase]);
      expect(filterCases([claimCase, grievanceCase, processCase], { kind: "other" })).toEqual([processCase]);
      expect(filterCases([claimCase, grievanceCase, processCase], { kind: "all" })).toHaveLength(3);
    });

    it("filters by overdue only", () => {
      const overdueCase = createMockCase(10, { sla_due_at: "2026-10-02T00:00:00Z" });
      const futureCase = createMockCase(11, { sla_due_at: "2026-10-08T00:00:00Z" });
      const filtered = filterCases([overdueCase, futureCase], { overdueOnly: true }, refNow);
      expect(filtered).toEqual([overdueCase]);
    });
  });

  describe("getQueueCounts", () => {
    it("computes counts for overdue, due today, due this week, and total", () => {
      const items = [
        createMockCase(1, { sla_due_at: "2026-10-02T10:00:00Z" }), // Overdue (-2 days)
        createMockCase(2, { sla_due_at: "2026-10-04T12:00:00Z" }), // Due today (0 days)
        createMockCase(3, { sla_due_at: "2026-10-07T10:00:00Z" }), // Due this week (3 days)
        createMockCase(4, { sla_due_at: "2026-10-20T10:00:00Z" }), // Next month (16 days)
        createMockCase(5, { sla_due_at: null }), // No SLA
      ];
      const counts = getQueueCounts(items, refNow);
      expect(counts.overdue).toBe(1);
      expect(counts.dueToday).toBe(1);
      expect(counts.dueThisWeek).toBe(2); // today (1) + in 3 days (1)
      expect(counts.total).toBe(5);
    });
  });
});

describe("P2.28d WorkQueuePage UI integration", () => {
  const mockCases: OfficeCase[] = Array.from({ length: 30 }, (_, i) => {
    const idx = i + 1;
    let sla: string | null = "2026-10-25T10:00:00Z";
    if (idx === 1) sla = "2026-10-01T10:00:00Z"; // overdue
    else if (idx === 2) sla = "2026-10-04T15:00:00Z"; // due today
    else if (idx === 3) sla = "2026-10-08T10:00:00Z"; // due this week

    return createMockCase(idx, {
      case_id: `CASE-${String(idx).padStart(4, "0")}`,
      claim_id: `CLM-${String(idx).padStart(4, "0")}`,
      sla_due_at: sla,
      amount_paise: (31 - idx) * 100000,
    });
  });

  function setupApiMocks(cases: OfficeCase[] = mockCases) {
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
            items: cases,
          },
          meta: { correlation_id: "c1", as_of: "2026-10-04" },
        };
      }
      if (path === "/api/v1/office/stopped-cases") {
        return { data: [], meta: { correlation_id: "c2", as_of: "2026-10-04" } };
      }
      throw new Error(`Unhandled api path: ${path}`);
    });
  }

  it("renders summary counts row (overdue, due today, due this week, total)", async () => {
    setupApiMocks();
    wrap(<WorkQueuePage />);

    expect(await screen.findByRole("heading", { name: /Cases waiting for action/i })).toBeTruthy();

    const metricsRegion = screen.getByLabelText(/Queue summary/i);
    expect(within(metricsRegion).getByText(/Overdue/i)).toBeTruthy();
    expect(within(metricsRegion).getByText(/Due today/i)).toBeTruthy();
    expect(within(metricsRegion).getByText(/Due this week/i)).toBeTruthy();
    expect(within(metricsRegion).getByText(/Total/i)).toBeTruthy();
    expect(within(metricsRegion).getByText("30")).toBeTruthy();
  });

  it("filters cases by text search", async () => {
    setupApiMocks();
    wrap(<WorkQueuePage />);

    expect(await screen.findByText("CASE-0001")).toBeTruthy();

    const searchInput = screen.getByRole("searchbox", { name: /Search/i });
    fireEvent.change(searchInput, { target: { value: "CLM-0012" } });

    expect(await screen.findByText("CASE-0012")).toBeTruthy();
    expect(screen.queryByText("CASE-0001")).toBeNull();
    expect(screen.queryByText("CASE-0020")).toBeNull();
  });

  it("paginates 30 mocked cases into 25 on page 1 and 5 on page 2", async () => {
    setupApiMocks();
    wrap(<WorkQueuePage />);

    expect(await screen.findByText("CASE-0001")).toBeTruthy();

    // Verify "Showing 1–25 of 30"
    expect(screen.getByText(/Showing 1[–-]25 of 30/i)).toBeTruthy();

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    // 1 header row + 25 data rows = 26 rows
    expect(rows.length).toBe(26);

    // Verify Previous button is disabled on page 1, Next button is enabled
    const prevButton = screen.getByRole("button", { name: /Previous/i }) as HTMLButtonElement;
    const nextButton = screen.getByRole("button", { name: /Next/i }) as HTMLButtonElement;
    expect(prevButton.disabled).toBe(true);
    expect(nextButton.disabled).toBe(false);

    // Click Next
    fireEvent.click(nextButton);

    // Verify "Showing 26–30 of 30"
    expect(screen.getByText(/Showing 26[–-]30 of 30/i)).toBeTruthy();

    const page2Rows = within(screen.getByRole("table")).getAllByRole("row");
    // 1 header row + 5 data rows = 6 rows
    expect(page2Rows.length).toBe(6);

    expect(screen.getByText("CASE-0026")).toBeTruthy();
    expect(screen.getByText("CASE-0030")).toBeTruthy();
    expect(screen.queryByText("CASE-0001")).toBeNull();

    // Next is now disabled, Previous is enabled
    expect(nextButton.disabled).toBe(true);
    expect(prevButton.disabled).toBe(false);
  });

  it("keeps each row's case link (<Link> with <code>) and the claim ID in its own cell", async () => {
    setupApiMocks();
    wrap(<WorkQueuePage />);

    expect(await screen.findByText("CASE-0001")).toBeTruthy();

    const caseLink = screen.getByRole("link", { name: "CASE-0001" });
    expect(caseLink).toBeTruthy();
    expect(caseLink.getAttribute("href")).toBe("/office/cases/CASE-0001");
    expect(caseLink.querySelector("code")?.textContent).toBe("CASE-0001");

    // Claim ID cell
    const claimCell = screen.getByText("CLM-0001");
    expect(claimCell).toBeTruthy();
    expect(claimCell.tagName.toLowerCase()).toBe("code");
  });

  it("shows empty state and allows clearing filters when no cases match", async () => {
    setupApiMocks();
    wrap(<WorkQueuePage />);

    expect(await screen.findByText("CASE-0001")).toBeTruthy();

    const searchInput = screen.getByRole("searchbox", { name: /Search/i });
    fireEvent.change(searchInput, { target: { value: "DOES_NOT_EXIST_XYZ" } });

    expect(await screen.findByText(/No cases match these filters/i)).toBeTruthy();
    const clearButton = screen.getByRole("button", { name: /Clear filters/i });
    expect(clearButton).toBeTruthy();

    // Clicking Clear filters resets everything
    fireEvent.click(clearButton);
    expect(await screen.findByText("CASE-0001")).toBeTruthy();
  });
});
