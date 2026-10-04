import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api } from "../api/client";
import "../i18n";
import { RetirementPage } from "./member/RetirementPage";
import { retirementRows, type PensionEstimate, type PfForecast, type PfScenario } from "./member/retirement";
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn() }));
afterEach(cleanup);

const scenario = (vpf: number, corpus: number, income: number, years = 0): PfScenario => ({ vpf_bp: vpf, corpus_paise: corpus, employee_paise: 0,
  employer_paise: 0, vpf_paise: 0, interest_paise: 0, months: 120, final_wages_paise: 4000000, monthly_income_paise: income,
  vpf_now_monthly_paise: vpf ? 250000 : 0, taxable_interest_years: Array.from({ length: years }, (_, i) => ({ financial_year: `20${30 + i}-${31 + i}`, own_contributions_paise: 1, above_threshold_paise: 1 })) });
const forecast = (vpf = 0): PfForecast => ({ as_of: "2026-10-04", retire_on: "2036-10-04", months_to_go: 120, balance_now_paise: 60000000,
  wages_now_paise: 2500000, in_service: true, note: "Illustrative.", scenarios: vpf ? [scenario(0, 300000000, 1500000), scenario(1000, 400000000, 2000000, 3)] : [scenario(0, 300000000, 1500000)],
  assumptions: { interest_rate_bp: 825, interest_declared_for: "2025-26", wage_growth_bp: 500, drawdown_rate_bp: 600, vpf_max_bp: 8800,
    taxable_interest_threshold_paise: 25000000, rule_version: "demo-rules-2026.2" } });
const pension: PensionEstimate = { rule_version: "demo", scenarios: [
  { label: "leave now", service_months: 100, eligible: false, monthly_paise: 0, reason: "At least 10 years of service are needed for a monthly pension." },
  { label: "stay to 58", service_months: 220, eligible: true, monthly_paise: 500000, working: "₹15,000 x 18 years / 70" }] };

it("adds the PF income and the pension and compares them with the wages at 58 (P2.23)", () => {
  const [now, vpf] = retirementRows(forecast(10), pension);
  expect(now).toMatchObject({ vpfPct: 0, pfIncome: 1500000, pension: 500000, total: 2000000, replacementPct: 50 });
  expect(vpf).toMatchObject({ vpfPct: 10, total: 2500000, replacementPct: 62.5, vpfNow: 250000, taxableYears: 3 });
  const left = { ...forecast(), in_service: false };
  expect(retirementRows(left, pension)[0].pension).toBe(0);                         // out of service: the "leave now" estimate
});

it("shows the view and the VPF what-if (P2.23)", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/members/me/retirement-forecast?vpf_pct=0") return { data: forecast(), meta: {} };
    if (path === "/api/v1/members/me/retirement-forecast?vpf_pct=10") return { data: forecast(10), meta: {} };
    if (path === "/api/v1/members/me/pension-eligibility-preview") return { data: pension, meta: {} };
    throw new Error(`unexpected ${String(path)}`);
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><RetirementPage /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "At 58" })).toBeTruthy();
  expect(await screen.findByText("50%")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Show with VPF" }));
  expect(await screen.findByText("62.5%")).toBeTruthy();
  expect(screen.getByText(/VPF costs ₹2,500(\.00)? a month now/)).toBeTruthy();
  expect(screen.getByText(/the interest on the part above it is taxable/)).toBeTruthy();
});
