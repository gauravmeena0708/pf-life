import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import "../i18n";
import { ReturnsPage } from "./employer/ReturnsPage";
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask: vi.fn(), request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let responses: Record<string, unknown>;
beforeEach(() => { vi.clearAllMocks(); responses = {};
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.signatory" });
  vi.mocked(api).mockImplementation(async (path) => ({ data: responses[path], meta: {} })); vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);

it("shows VISHWAS, 2026: each 14B demand recalculated, or why it is not eligible", async () => {
  const base = "/api/v1/employers/me";
  responses[`${base}/returns/dashboard`] = []; responses[`${base}/demands`] = { items: [] };
  responses[base] = { establishment_id: "EST-DEMO-0001" };
  responses[`${base}/compliance-summary`] = { establishment_id: "EST-DEMO-0001", as_of: "2026-10-01", counts: {}, months: [] };
  responses[`${base}/vishwas-applications`] = {
    applications: [], scheme: { scheme: "VISHWAS, 2026", open_from: "2026-06-29", open_until: "2026-12-28", defaults_before: "2024-06-14" },
    open_14b_demands: [{ demand_id: "DEM-A", wage_month: "2023-06", amount_paise: 500000, working: "200 days late on ₹50,000" },
                       { demand_id: "DEM-B", wage_month: "2024-08", amount_paise: 300000, working: "30 days late on ₹40,000" }],
    assessment: [
      { demand_id: "DEM-A", eligible: true, reasons: [], damages_paise: 500000, arrears_paise: 5000000, months_of_default: 6.6, rate_pct_per_month: 1, revised_paise: 328700 },
      { demand_id: "DEM-B", eligible: false, reasons: ["Only defaults before 2024-06-14 are covered."], damages_paise: 300000, arrears_paise: 4000000,
        months_of_default: 1, rate_pct_per_month: 0.25, revised_paise: null }] };
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><ReturnsPage /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText((_, el) => el?.tagName === "P" && /^VISHWAS, 2026, open 2026-06-29 to 2026-12-28/.test(el.textContent ?? ""))).toBeTruthy();
  expect(screen.getByText(/× 1% × 6.6 months =/)).toBeTruthy();
  expect(screen.getByText(/not eligible: Only defaults before 2024-06-14/)).toBeTruthy();
  const box = (id: string) => screen.getAllByRole("checkbox").find((b) => (b.parentElement?.textContent ?? "").startsWith(id)) as HTMLInputElement;
  expect(box("DEM-B").disabled).toBe(true);
  expect(box("DEM-A").disabled).toBe(false);
  expect(screen.getByLabelText(/undertake not to pursue any further appeal/)).toBeTruthy();
});
