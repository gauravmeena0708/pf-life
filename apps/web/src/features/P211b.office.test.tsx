import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import { menusFor } from "../data/navigation";
import "../i18n";
import { InquiriesPage } from "./office/InquiriesPage";
const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let responses: Record<string, unknown>;
const as = (stakeholder: string) => vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder });
beforeEach(() => { vi.clearAllMocks(); ask.mockResolvedValue("step-token"); responses = { "/api/v1/office/compliance/inspections": [] };
  vi.mocked(api).mockImplementation(async (path) => ({ data: responses[path], meta: {} })); vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);
function show(page: ReactElement) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const listed = (kind: string) => [{ case_id: "CMP-1", establishment_id: "EST-1", legal_name: "Synthetic Textiles", kind, state: "OPEN" }];
const caseWith = (inquiry: Record<string, unknown>, kind = "INQUIRY_7A") => ({ case_id: "CMP-1", establishment_id: "EST-1", legal_name: "Synthetic Textiles", kind, state: "OPEN",
  inquiry: { diary_no: "EPR/RO-DEMO-01/2026/0009", officer_rank: "APFC", officer_subject: "x", period_from: "2025-04", period_to: "2025-09", contributory_uans: 40, order_due_at: null, ...inquiry } });
async function openCase() { fireEvent.click(await screen.findByRole("button", { name: "Open" })); }

it("lets the DA draft a damages notice from the desk review", async () => {
  as("fo.da_compliance"); responses["/api/v1/office/compliance/cases"] = [];
  show(<InquiriesPage />);
  const form = await screen.findByRole("form", { name: "Damages notice (14B / 7Q)" });
  fireEvent.change(within(form).getByLabelText(/Contributory UANs/), { target: { value: "40" } });
  fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Periodic desk review" } });
  fireEvent.click(within(form).getByRole("button", { name: "Draft notice" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases", { establishment_id: "EST-DEMO-0001", kind: "INQUIRY_14B", contributory_uans: 40, note: "Periodic desk review" }));
});

it("passes the 14B order with reasons and the 7Q order at the statutory amount", async () => {
  as("fo.apfc"); responses["/api/v1/office/compliance/cases"] = listed("INQUIRY_14B");
  responses["/api/v1/office/compliance/cases/CMP-1"] = caseWith({ state: "CONCLUDED", section: "14B", actions: [{ kind: "NOTICE_DRAFT", at: "x", detail: { demands: [
    { demand_id: "D1", kind: "DAMAGES_14B", wage_month: "2025-06", days_late: 90, amount_paise: 300000 },
    { demand_id: "D2", kind: "INTEREST_7Q", wage_month: "2025-06", days_late: 90, amount_paise: 120000 }] } }] }, "INQUIRY_14B");
  show(<InquiriesPage />); await openCase();
  const d14 = await screen.findByRole("form", { name: "Pass 14B order" });
  fireEvent.change(within(d14).getByLabelText(/worked out ₹3,000/), { target: { value: "2000" } });
  fireEvent.change(within(d14).getByLabelText("Findings and reasons"), { target: { value: "Bank strike" } });
  fireEvent.click(within(d14).getByRole("button", { name: "Pass 14B order" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "pass-order", amountPaise: 200000 })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-1/orders",
    { kind: "14B", levies: [{ demand_id: "D1", amount_paise: 200000 }], reasoning: "Bank strike", ex_parte: false }, { stepUpToken: "step-token" }));
  const q7 = screen.getByRole("form", { name: "Pass 7Q order" });
  expect((within(q7).getByLabelText(/worked out ₹1,200/) as HTMLInputElement).readOnly).toBe(true);
});

it("decides a review on the employer's application with the next-higher officer's view, and reopens under 7C", async () => {
  as("fo.apfc"); responses["/api/v1/office/compliance/cases"] = listed("INQUIRY_7A");
  responses["/api/v1/office/compliance/cases/CMP-1"] = caseWith({ state: "ORDERED", section: "7A", actions: [
    { kind: "APPLICATION", at: "x", detail: { application_id: "APP-1", kind: "REVIEW_7B", grounds: "NEW_EVIDENCE", text: "Register found", status: "PENDING" } }] });
  show(<InquiriesPage />); await openCase();
  const review = await screen.findByRole("form", { name: "Review under 7B" });
  expect(within(review).getByLabelText(/View of the RPFC-II/)).toBeTruthy();
  fireEvent.change(within(review).getByLabelText(/View of the RPFC-II/), { target: { value: "Fit for review" } });
  fireEvent.change(within(review).getByLabelText("Note"), { target: { value: "New evidence" } });
  fireEvent.click(within(review).getByRole("button", { name: "Decide review" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-1/reviews-7b",
    { application_id: "APP-1", view_by_rank: "RPFC-II", view_note: "Fit for review", decision: "GRANTED", note: "New evidence" }, { stepUpToken: "step-token" }));
  const reopen = screen.getByRole("form", { name: "Reopen under 7C" });
  fireEvent.change(within(reopen).getByLabelText("Reason"), { target: { value: "GSTN data" } });
  fireEvent.click(within(reopen).getByRole("button", { name: "Reopen under 7C" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-1/escaped-assessments-7c",
    { reason_type: "OMISSION_BY_EMPLOYER", reason: "GSTN data" }, { stepUpToken: "step-token" }));
});

it("shows the set-aside decision when the employer applies against an ex-parte order", async () => {
  as("fo.apfc"); responses["/api/v1/office/compliance/cases"] = listed("INQUIRY_7A");
  responses["/api/v1/office/compliance/cases/CMP-1"] = caseWith({ state: "ORDERED", section: "7A", actions: [
    { kind: "APPLICATION", at: "x", detail: { application_id: "APP-2", kind: "SET_ASIDE", grounds: "NOT_SERVED", text: "Old address", status: "PENDING" } }] });
  show(<InquiriesPage />); await openCase();
  const form = await screen.findByRole("form", { name: "Decide set-aside" });
  fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Not served" } });
  fireEvent.click(within(form).getByRole("button", { name: "Decide" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-1/set-asides",
    { application_id: "APP-2", decision: "SET_ASIDE", note: "Not served" }, { stepUpToken: "step-token" }));
});

it("lists orders due for scrutiny and records one; the Zonal ACC has a menu link", async () => {
  as("zo.acc"); const month = new Date().toISOString().slice(0, 7);
  responses[`/api/v1/office/compliance/scrutinies?month=${month}`] = [{ case_id: "CMP-7", diary_no: "EPR/RO-DEMO-01/2026/0007", establishment_id: "EST-1",
    officer_rank: "RPFC-I", ordered_at: "2026-10-01T10:00:00Z", scrutiny_due: "2026-11-15", scrutinised: false, overdue: false }];
  show(<InquiriesPage />);
  const item = await screen.findByRole("article", { name: "Scrutiny EPR/RO-DEMO-01/2026/0007" });
  fireEvent.change(within(item).getByLabelText(/Observations/), { target: { value: "Reasons adequate" } });
  fireEvent.click(within(item).getByRole("button", { name: "Record scrutiny" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-7/scrutinies", { observations: "Reasons adequate", direct_7c: false }));
  expect(menusFor("zo.acc")).toContainEqual({ label: "Scrutiny of orders", to: "/office/inquiries#scrutiny-heading" });
});
