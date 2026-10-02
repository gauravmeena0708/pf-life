import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import "../i18n";
import { EecSection } from "./employer/EecSection";
import { ReturnsPage } from "./employer/ReturnsPage";
const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
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

it("works out the EEC, 2026 dues of a left-out employee and declares them with step-up", async () => {
  ask.mockResolvedValue("step-token");
  const totals = { AC01_EPF_EE: 0, AC01_EPF_ER: 1584000, AC10_EPS: 3600000, AC21_EDLI: 216000, AC02_ADMIN: 216000, INTEREST_7Q: 500000, DAMAGES_14B: 10000, TOTAL: 6126000 };
  responses["/api/v1/employers/me/eec-declarations"] = {
    scheme: { scheme: "EEC, 2026", open_from: "2026-07-01", open_until: "2026-10-31", joined_from: "2009-04-01", joined_until: "2026-03-31", damages_paise: 10000 },
    open: true, candidates: [{ uan: "100000000777", name: "LEFT OUT DEMO", date_of_joining: "2023-04-10" }], declarations: [] };
  responses["/api/v1/employers/me/eec-declarations/dues?uan=100000000777&monthly_wages_paise=1200000&employee_share_deducted=false"] =
    { from_month: "2023-04", to_month: "2026-03", months: new Array(36).fill({}), totals_paise: totals, employee_share_waived: true };
  vi.mocked(command).mockResolvedValueOnce({ data: { from_month: "2023-04", to_month: "2026-03", months: [], totals_paise: totals, employee_share_waived: true, trrn: "TRRN9" }, meta: {} });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><EecSection signatory /></MemoryRouter></QueryClientProvider>);
  const form = await screen.findByRole("form", { name: "EEC declaration" });
  fireEvent.change(within(form).getByLabelText("Monthly wages (₹)"), { target: { value: "12000" } });
  fireEvent.click(within(form).getByLabelText(/I declare/));
  fireEvent.click(within(form).getByRole("button", { name: "Work out the dues" }));
  expect(await within(form).findByText(/36 months\) — employee's share waived/)).toBeTruthy();
  expect(within(form).getByText(/₹61,260/, { selector: "strong" })).toBeTruthy();
  fireEvent.click(within(form).getByRole("button", { name: "Declare and raise the challan" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "declare-eec", resourceId: "100000000777", amountPaise: 6126000 })));
  await waitFor(() => expect(command).toHaveBeenLastCalledWith("POST", "/api/v1/employers/me/eec-declarations",
    { uan: "100000000777", monthly_wages_paise: 1200000, employee_share_deducted: false, declaration: true }, { stepUpToken: "step-token" }));
  expect(await screen.findByText(/Challan TRRN9 raised/)).toBeTruthy();
});
