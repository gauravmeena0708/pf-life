import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { ActuarialExtractPage, rowsCsv } from "./pension/ActuarialExtractPage";
import { DisbursementListsPage } from "./pension/DisbursementListsPage";
import { PensionOfficePage } from "./pension/PensionOfficePage";
import { ClaimToolsPage } from "./office/ClaimToolsPage";
import { HigherPensionPage } from "./member/HigherPensionPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({ ...await importOriginal<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
const option = { option_id: "HPO-1", uan: "100000000001", account_link_id: "AL-1", state: "VALIDATED", dues_paise: 123400,
  wages: [], working: "Calculated dues", next_step: "The APFC decides the option." };
let responses: Record<string, unknown>; let clients: QueryClient[];
beforeEach(() => {
  vi.clearAllMocks(); clients = [];
  responses = { "/api/v1/office/pensions/higher-pension-options?state=VALIDATED": [option],
    "/api/v1/office/pensions/higher-pension-options?state=APPROVED": [{ ...option, state: "APPROVED" }],
    "/api/v1/office/pensions/life-certificates/overdue": [], "/api/v1/office/pensions/updation-activities": [],
    "/api/v1/office/pensions/disbursement-lists?month=2026-08": { month: "2026-08", banks: [{ bank: "SBIN", pensioners: 1, amount_paise: 250000,
      items: [{ ppo_id: "PPO-1", name_masked: "A****", account_last4: "1234", amount_paise: 250000 }] }], totals: { pensioners: 1, amount_paise: 250000 }, note: "Legacy lists." },
    "/api/v1/ho/actuarial/extracts?as_of=2026-08-31": { as_of: "2026-08-31", aggregates: [{ category: "PENSIONER", age_band: "60-64", count: 1 }],
      rows: [{ record_id: "hashed-1", category: "PENSIONER", age_years: 61, gender: null, pension_start_year: 2020,
        monthly_pension_paise: 250000, service_months: 240, status: "IN_PAYMENT" }], rule_version: "v1", note: "No identifiers." } };
  vi.mocked(api).mockImplementation(async (path) => {
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockImplementation(async (_method, path) => ({ data: path.includes("ledger-transfers") ? { ...option, state: "TRANSFER_REQUESTED", next_step: "Transfer in progress." }
    : path.includes("special-10d") ? { case_id: "S10D-1", state: "OPEN", checklist: ["Reconstruct wages."], next_step: "APFC accepts the record." }
    : { ...option, state: "APPROVED", next_step: "DA requests transfer." }, meta: {} }));
  ask.mockResolvedValue("token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });
function renderPage(page: ReactElement, role: string) {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>);
}
it("decides a validated higher-pension option with an amount-bound step-up", async () => {
  renderPage(<PensionOfficePage />, "fo.apfc_pension");
  const note = await screen.findByLabelText("Decision note for HPO-1"); fireEvent.change(note, { target: { value: "Records checked and approved." } });
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/pensions/higher-pension-options/HPO-1/decisions",
    { decision: "APPROVE", note: "Records checked and approved." }, { stepUpToken: "token" }));
  expect(ask).toHaveBeenCalledWith({ action: "decide-higher-pension", resourceId: "HPO-1", amountPaise: 123400, summary: expect.any(String) });
});
it("requests transfer with step-up and an idempotency key", async () => {
  renderPage(<ClaimToolsPage />, "fo.da_accounts"); fireEvent.click(await screen.findByRole("button", { name: "Request dues transfer" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/pensions/higher-pension-options/HPO-1/ledger-transfers",
    undefined, { stepUpToken: "token", idempotencyKey: expect.any(String) }));
  expect(ask).toHaveBeenCalledWith({ action: "transfer-higher-pension-dues", resourceId: "HPO-1", amountPaise: 123400, summary: expect.any(String) });
  expect(await screen.findByText(/Transfer in progress/)).toBeTruthy();
});
it("submits the Special 10D missing items, details and evidence", async () => {
  renderPage(<PensionOfficePage />, "fo.da_pension"); const form = await screen.findByRole("form", { name: "Open Special 10D case" });
  fireEvent.change(within(form).getByLabelText("UAN"), { target: { value: "100000000001" } });
  fireEvent.click(within(form).getByLabelText("Wages"));
  fireEvent.change(within(form).getByLabelText("Details"), { target: { value: "Payroll records are missing for this period." } });
  fireEvent.change(within(form).getByLabelText("Reference"), { target: { value: "CERT-1" } });
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/pensions/special-10d-cases", {
    uan: "100000000001", missing: ["WAGES"], details: "Payroll records are missing for this period.",
    evidence: [{ kind: "EMPLOYER_CERTIFICATE", ref: "CERT-1" }],
  }));
  expect(await screen.findByText("Reconstruct wages.")).toBeTruthy(); expect(screen.getByText("APFC accepts the record.")).toBeTruthy();
});
it("shows bank-wise disbursement totals", async () => {
  renderPage(<DisbursementListsPage />, "fo.pension_disbursement");
  fireEvent.change(await screen.findByLabelText("Payment month"), { target: { value: "2026-08" } });
  expect(await screen.findByText("PPO-1")).toBeTruthy(); expect(screen.getByText("Bank SBIN")).toBeTruthy();
  expect(screen.getByText(/1 pensioners · ₹2,500/)).toBeTruthy(); expect(screen.getByRole("button", { name: "Print" })).toBeTruthy();
});
it("renders only de-identified actuarial rows and creates CSV", async () => {
  renderPage(<ActuarialExtractPage />, "ho.actuarial");
  fireEvent.change(await screen.findByLabelText("As-of date"), { target: { value: "2026-08-31" } });
  expect(await screen.findByText("hashed-1")).toBeTruthy(); expect(screen.queryByText("UAN")).toBeNull(); expect(screen.queryByText("Name")).toBeNull();
  expect(rowsCsv((responses["/api/v1/ho/actuarial/extracts?as_of=2026-08-31"] as { rows: Parameters<typeof rowsCsv>[0] }).rows)).toContain('"hashed-1"');
  const createUrl = vi.fn(() => "blob:extract"); const revokeUrl = vi.fn();
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeUrl });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
  expect(createUrl).toHaveBeenCalledWith(expect.any(Blob)); expect(click).toHaveBeenCalled(); expect(revokeUrl).toHaveBeenCalledWith("blob:extract");
  Reflect.deleteProperty(URL, "createObjectURL"); Reflect.deleteProperty(URL, "revokeObjectURL"); click.mockRestore();
});
it("shows the member's new higher-pension state and API next step", async () => {
  responses["/api/v1/members/me"] = { uan: option.uan };
  responses["/api/v1/members/me/higher-pension-options"] = { options: [{ ...option, state: "TRANSFER_FAILED", next_step: "The member deposits the difference through the office (VDR)." }],
    in_service_on: "2022-09-01", note: "Illustrative option." };
  renderPage(<HigherPensionPage />, "member");
  expect(await screen.findByText("Dues transfer failed")).toBeTruthy();
  expect(screen.getByText("The member deposits the difference through the office (VDR).")).toBeTruthy();
});
it.each([["fo.pension_disbursement", "/office/pension-disbursement", "Disbursement lists"], ["ho.actuarial", "/ho/actuarial", "Actuarial extract"]])("routes %s to its page", (role, path, label) => {
  expect(menusFor(role)).toEqual([{ label, to: path }]); expect(homeFor(role)).toBe(path);
});
