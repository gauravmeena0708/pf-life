import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api } from "../api/client";
import "../i18n";
import { EpsRectificationSection, type Rectification } from "./office/EpsRectification";
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn() }));
afterEach(cleanup);

const proposed: Rectification = { rectification_id: "EPSR-1", account_link_id: "AL-0001", uan: "100000000001", scenario: "WRONGLY_ALLOWED",
  scenario_label: "I — EPS allowed to a member not eligible", exempted_trust: null, from_month: "2026-08", to_month: "2026-08", total_paise: 125600,
  notesheet_no: "NS/1", remarks: "Joined in 2016 on ₹40,000", state: "PROPOSED", decision_note: null, journal_id: null, trust_reference: null,
  circular: "HO circular WSU/2025/E-961539 (19 Dec 2025)",
  worksheet: { months: [{ wage_month: "2026-08", basis: "EPS remitted", amount_paise: 125000, rate_bp: 825, months: 1, interest_paise: 600 }],
    amount_paise: 125000, interest_paise: 600, total_paise: 125600, worked_out_on: "2026-10-04" } };

const show = (role: string, rows: Rectification[]) => {
  vi.mocked(api).mockResolvedValue({ data: rows, meta: {} });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>
    <EpsRectificationSection role={role} /></MemoryRouter></QueryClientProvider>);
};

it("shows the APFC the month-by-month working and the move to approve (P2.19c)", async () => {
  show("fo.apfc", [proposed]);
  expect(await screen.findByRole("table", { name: "Working of EPSR-1" })).toBeTruthy();
  expect(screen.getByText(/0.25|8.25% for 1 months/)).toBeTruthy();
  expect(screen.getByText("Total A/c 10 → A/c 1")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  expect(screen.queryByRole("form", { name: "Work out an EPS rectification" })).toBeNull();
});

it("lets the DA work one out, and Cash record a trust's remittance (P2.19c)", async () => {
  show("fo.da_accounts", []);
  expect(await screen.findByRole("form", { name: "Work out an EPS rectification" })).toBeTruthy();
  cleanup();
  show("fo.cash", [{ ...proposed, scenario: "WRONGLY_DENIED", exempted_trust: "Demo Steel Works PF Trust", state: "AWAITING_TRUST_REMITTANCE" }]);
  expect(await screen.findByRole("button", { name: /Record ₹1,256/ })).toBeTruthy();
  expect(screen.getByText("Total trust → A/c 10")).toBeTruthy();
});
