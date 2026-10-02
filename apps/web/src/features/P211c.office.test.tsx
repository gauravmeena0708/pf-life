import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import "../i18n";
import { EmployerProceedingsPage } from "./employer/ProceedingsPage";
import { InquiriesPage } from "./office/InquiriesPage";
const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let responses: Record<string, unknown>;
const as = (stakeholder: string) => vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder });
beforeEach(() => { vi.clearAllMocks(); ask.mockResolvedValue("step-token");
  responses = { "/api/v1/office/compliance/inspections": [], "/api/v1/office/compliance/cases": [], "/api/v1/office/compliance/prosecutions": [] };
  vi.mocked(api).mockImplementation(async (path) => ({ data: responses[path], meta: {} })); vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);
function show(page: ReactElement) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const prosecution = (state: string, extra = {}) => ({ prosecution_id: "PRS-1", establishment_id: "EST-1", inquiry_case_id: "CMP-1", offence: "NON_FILING_RETURNS",
  particulars: "July return not filed", state, reply_due: "2026-10-12T10:00:00Z", reply_overdue: false, legal_case_id: null,
  history: [{ step: "SCN_ISSUED", by: "fo.apfc", at: "2026-10-02T10:00:00Z", note: "Issued" }], ...extra });

it("lets the SS register a 26B dispute with each employee, after a one-time code", async () => {
  as("fo.ss"); show(<InquiriesPage />);
  const form = await screen.findByRole("form", { name: "Membership dispute (Para 26B)" });
  fireEvent.change(within(form).getByLabelText("Contributory UANs"), { target: { value: "40" } });
  fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "WORKER A" } });
  fireEvent.change(within(form).getByLabelText("Member from (claimed)"), { target: { value: "2025-01-01" } });
  fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Apprentice says he is a worker" } });
  fireEvent.click(within(form).getByRole("button", { name: "Register dispute" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "register-26b", resourceId: "EST-DEMO-0001" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/membership-disputes", expect.objectContaining({
    trigger: "EMPLOYEE_COMPLAINT", contributory_uans: 40, employees: [{ name: "WORKER A", claimed_from: "2025-01-01" }] }), { stepUpToken: "step-token" }));
});

it("passes a 26B order deciding each disputed employee", async () => {
  as("fo.apfc"); responses["/api/v1/office/compliance/cases"] = [{ case_id: "CMP-26", establishment_id: "EST-1", legal_name: "S", kind: "INQUIRY_26B", state: "OPEN" }];
  responses["/api/v1/office/compliance/cases/CMP-26"] = { case_id: "CMP-26", establishment_id: "EST-1", legal_name: "S", kind: "INQUIRY_26B", state: "OPEN",
    inquiry: { diary_no: "EPR/X/2026/0026", officer_rank: "RPFC-II", officer_subject: "x", state: "CONCLUDED", section: "26B", period_from: "2025-01", period_to: "2026-10",
      contributory_uans: 40, order_due_at: null, actions: [{ kind: "DISPUTE", at: "x", detail: { employees: [{ name: "WORKER A", claimed_from: "2025-01-01" }, { name: "WORKER B", claimed_from: "2025-03-01" }] } }] } };
  show(<InquiriesPage />); fireEvent.click(await screen.findByRole("button", { name: "Open" }));
  const form = await screen.findByRole("form", { name: "Pass 26B order" });
  fireEvent.change(within(form).getAllByLabelText("Decision")[1], { target: { value: "no" } });
  fireEvent.change(within(form).getByLabelText("Findings and reasons"), { target: { value: "B is an apprentice" } });
  fireEvent.click(within(form).getByRole("button", { name: "Pass 26B order" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-26/orders", { kind: "26B", reasoning: "B is an apprentice", ex_parte: false,
    decisions: [{ name: "WORKER A", eligible: true, from_date: "2025-01-01" }, { name: "WORKER B", eligible: false }] }, { stepUpToken: "step-token" }));
});

it("routes a prosecution: the RPFC sanctions after the reply, the EO files the complaint", async () => {
  as("fo.oic"); responses["/api/v1/office/compliance/prosecutions"] = [prosecution("REPLIED")];
  show(<InquiriesPage />);
  const sanction = await screen.findByRole("form", { name: "SANCTION PRS-1" });
  fireEvent.change(within(sanction).getByLabelText("Note"), { target: { value: "Reply not satisfactory" } });
  fireEvent.click(within(sanction).getByRole("button", { name: "Sanction prosecution" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/prosecutions/PRS-1/steps", { step: "SANCTION", note: "Reply not satisfactory" }));
  cleanup(); as("fo.eo"); responses["/api/v1/office/compliance/prosecutions"] = [prosecution("SANCTIONED")];
  show(<InquiriesPage />);
  const complaint = await screen.findByRole("form", { name: "COMPLAINT PRS-1" });
  fireEvent.change(within(complaint).getByLabelText("Court"), { target: { value: "CJM Delhi" } });
  fireEvent.change(within(complaint).getByLabelText("Complaint number"), { target: { value: "CC 55/2026" } });
  fireEvent.change(within(complaint).getByLabelText("Note"), { target: { value: "Filed" } });
  fireEvent.click(within(complaint).getByRole("button", { name: "Record complaint filed" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/prosecutions/PRS-1/steps",
    { step: "COMPLAINT", note: "Filed", court: "CJM Delhi", complaint_no: "CC 55/2026" }));
  cleanup(); as("fo.apfc"); responses["/api/v1/office/compliance/prosecutions"] = [prosecution("COMPLAINT_FILED")];
  show(<InquiriesPage />);
  expect(await screen.findByText("Complaint in court")).toBeTruthy();
  expect(screen.queryByRole("form", { name: "DROP PRS-1" })).toBeNull();                          // too late to drop
});

it("lets the employer reply to a prosecution show-cause notice", async () => {
  as("employer.owner"); responses["/api/v1/employers/me/proceedings"] = []; responses["/api/v1/employers/me/prosecutions"] = [prosecution("SCN_ISSUED")];
  show(<EmployerProceedingsPage />);
  const form = await screen.findByRole("form", { name: "Reply to PRS-1" });
  fireEvent.change(within(form).getByLabelText("Reply"), { target: { value: "Delayed by a software failure" } });
  fireEvent.click(within(form).getByRole("button", { name: "Send reply" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/employers/me/prosecutions/PRS-1/replies", { text: "Delayed by a software failure", documents: [] }));
});
