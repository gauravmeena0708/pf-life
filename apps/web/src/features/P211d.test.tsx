import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { EmployerProceedingsPage } from "./employer/ProceedingsPage";
import { ComplianceReportsPage } from "./ho/ComplianceReportsPage";
import { InquiriesPage } from "./office/InquiriesPage";
import { RecoveryPage } from "./office/RecoveryPage";
const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let responses: Record<string, unknown>;
const as = (stakeholder: string) => vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder });
beforeEach(() => { vi.clearAllMocks(); ask.mockResolvedValue("step-token"); responses = {};
  vi.mocked(api).mockImplementation(async (path) => ({ data: responses[path], meta: {} })); vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);
function show(page: ReactElement) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const rc = (state: string, extra = {}) => ({ recovery_case_id: "RC-1", establishment_id: "EST-DEMO-0002", inquiry_case_id: "CMP-SEED-0002", certificate_no: "RC/RO-DEMO-01/2026/1234",
  amount_paise: 3000000, realised_paise: 0, outstanding_paise: 3000000, state, pay_by: null, stayed: false, actions: [], ...extra });

it("lets the officer certify an unpaid order and issue an 8F notice bound to the amount", async () => {
  as("fo.apfc"); responses["/api/v1/office/compliance/inspections"] = []; responses["/api/v1/office/compliance/prosecutions"] = [];
  responses["/api/v1/office/compliance/cases"] = [{ case_id: "CMP-SEED-0002", establishment_id: "EST-DEMO-0002", legal_name: "Demo Engineering Works", kind: "INQUIRY_7A", state: "CLOSED" }];
  responses["/api/v1/office/compliance/cases/CMP-SEED-0002"] = { case_id: "CMP-SEED-0002", establishment_id: "EST-DEMO-0002", legal_name: "Demo Engineering Works", kind: "INQUIRY_7A", state: "CLOSED",
    inquiry: { diary_no: "EPR/RO-DEMO-01/2026/0900", officer_rank: "APFC", officer_subject: "x", state: "ORDERED", section: "7A", period_from: "2025-01", period_to: "2025-06", contributory_uans: 60, order_due_at: null, actions: [] } };
  show(<InquiriesPage />); fireEvent.click(await screen.findByRole("button", { name: "Open" }));
  const cert = await screen.findByRole("form", { name: "Issue recovery certificate" });
  fireEvent.change(within(cert).getByLabelText("Note"), { target: { value: "Unpaid since June" } });
  fireEvent.click(within(cert).getByRole("button", { name: "Issue certificate" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-SEED-0002/recovery-certificates", { note: "Unpaid since June" }, { stepUpToken: "step-token" }));
  const f8 = screen.getByRole("form", { name: "Notice under 8F" });
  fireEvent.change(within(f8).getByLabelText("Name"), { target: { value: "Demo Bank" } });
  fireEvent.change(within(f8).getByLabelText("Account or debt"), { target: { value: "AC-1" } });
  fireEvent.change(within(f8).getByLabelText("Amount (₹)"), { target: { value: "5000" } });
  fireEvent.click(within(f8).getByRole("button", { name: "Issue 8F notice" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "garnishee-8f", amountPaise: 500000 })));
});

it("walks the Recovery Officer from the demand notice to a sale bound to its price", async () => {
  as("fo.recovery_officer"); responses["/api/v1/office/recovery/cases"] = [rc("CERTIFIED")];
  show(<RecoveryPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Serve demand notice (EPFCP-1)" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/recovery/RC-1/demand-notices"));
  cleanup(); responses["/api/v1/office/recovery/cases"] = [rc("IN_EXECUTION", { pay_by: "2026-10-17T10:00:00Z",
    actions: [{ kind: "ATTACHMENT", at: "2026-10-02T10:00:00Z", detail: { attachment_id: "ATT-1", description: "Two lathes" } }] })];
  show(<RecoveryPage />);
  const sale = await screen.findByRole("form", { name: "Sale RC/RO-DEMO-01/2026/1234" });
  fireEvent.change(within(sale).getByLabelText("Reserve price (₹)"), { target: { value: "12000" } });
  fireEvent.change(within(sale).getByLabelText("Sale price (₹)"), { target: { value: "13000" } });
  fireEvent.change(within(sale).getByLabelText("Buyer"), { target: { value: "Synthetic Traders" } });
  fireEvent.click(within(sale).getByRole("button", { name: "Record sale" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "sell-property", amountPaise: 1300000 })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/recovery/RC-1/sales",
    { attachment_id: "ATT-1", reserve_price_paise: 1200000, sale_price_paise: 1300000, buyer: "Synthetic Traders" }, { stepUpToken: "step-token" }));
  const arrest = screen.getByRole("form", { name: "Arrest RC/RO-DEMO-01/2026/1234" });
  fireEvent.change(within(arrest).getByLabelText("Hearing on (notice)"), { target: { value: "2026-11-10" } });
  fireEvent.change(within(arrest).getByLabelText("Reasons"), { target: { value: "EPFCP-25" } });
  fireEvent.click(within(arrest).getByRole("button", { name: "Record" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/recovery/RC-1/arrest-warrants",
    { step: "SHOW_CAUSE", reasons: "EPFCP-25", hearing_on: "2026-11-10" }, { stepUpToken: "step-token" }));
});

it("lets the RPFC grant instalments; shows a stay", async () => {
  as("fo.oic"); responses["/api/v1/office/recovery/cases"] = [rc("NOTICE_SERVED", { stayed: true })];
  show(<RecoveryPage />);
  expect(await screen.findByText("Stayed by a court")).toBeTruthy();
  const form = screen.getByRole("form", { name: "Instalments RC/RO-DEMO-01/2026/1234" });
  fireEvent.change(within(form).getByLabelText(/Number/), { target: { value: "6" } });
  fireEvent.change(within(form).getByLabelText("First due"), { target: { value: "2026-11-01" } });
  fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Hardship" } });
  fireEvent.change(within(form).getByLabelText("Bank guarantee (₹)"), { target: { value: "5000" } });
  fireEvent.change(within(form).getByLabelText("Guarantee reference"), { target: { value: "BG-1" } });
  fireEvent.click(within(form).getByRole("button", { name: "Grant" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/recovery/RC-1/instalments",
    { count: 6, first_due: "2026-11-01", note: "Hardship", bank_guarantee_paise: 500000, bank_guarantee_ref: "BG-1" }));
});

it("lets the Recovery Officer withdraw instalments on a default (P2.26)", async () => {
  as("fo.recovery_officer"); responses["/api/v1/office/recovery/cases"] = [rc("INSTALMENTS")];
  show(<RecoveryPage />);
  const form = await screen.findByRole("form", { name: "Default RC/RO-DEMO-01/2026/1234" });
  fireEvent.change(within(form).getByLabelText("What was missed"), { target: { value: "December instalment" } });
  fireEvent.click(within(form).getByRole("button", { name: "Withdraw the facility" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/recovery/RC-1/instalment-defaults", { missed: "December instalment" }));
});

it("shows the employer its recovery and HO its reports; menus", async () => {
  as("employer.owner"); responses["/api/v1/employers/me/proceedings"] = []; responses["/api/v1/employers/me/prosecutions"] = [];
  responses["/api/v1/employers/me/recovery-cases"] = [rc("NOTICE_SERVED", { realised_paise: 1000000, outstanding_paise: 2000000, pay_by: "2026-10-17T10:00:00Z" })];
  show(<EmployerProceedingsPage />);
  expect(await screen.findByRole("heading", { name: "Recovery of arrears" })).toBeTruthy();
  expect(screen.getByText("₹20,000.00")).toBeTruthy();
  cleanup(); as("ho.compliance");
  responses["/api/v1/ho/reports/proceedings"] = { as_of: "x", inquiries: 5, pending: 2, disposed_this_month: 3, average_days_to_order: 40, by_section: { "7A": { ORDERED: 3 } },
    pending_by_office: { "RO-DEMO-01": 2 }, orders_overdue: [], legal_cases: { "APPEAL_7I PENDING": 1 } };
  responses["/api/v1/ho/reports/recovery"] = { as_of: "x", certificates: 1, open: 1, certified_paise: 3000000, realised_paise: 1000000, outstanding_paise: 2000000,
    realised_by_mode_paise: { SALE: 1000000 }, stayed_paise: 0, in_instalments: 0, older_than_a_year: 0, by_state: {} };
  show(<ComplianceReportsPage />);
  expect(await screen.findByRole("heading", { name: "e-Proceedings" })).toBeTruthy();
  expect(screen.getByText(/Realised by mode: SALE ₹10,000/)).toBeTruthy();
  expect(menusFor("fo.recovery_officer").flatMap((g) => g.items ?? [])).toContainEqual(expect.objectContaining({ to: "/office/recovery" }));
  expect(menusFor("ho.recovery")).toEqual([{ label: "Proceedings and recovery", to: "/ho/compliance-reports" }]);
  expect(homeFor("fo.recovery_officer")).toBe("/office/recovery");
});
