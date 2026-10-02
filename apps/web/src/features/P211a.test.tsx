import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { InquiriesPage } from "./office/InquiriesPage";
import { EmployerProceedingsPage } from "./employer/ProceedingsPage";
const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let responses: Record<string, unknown>;
const as = (stakeholder: string) => vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder });
beforeEach(() => { vi.clearAllMocks(); ask.mockResolvedValue("step-token"); responses = {}; vi.mocked(api).mockImplementation(async (path) => ({ data: responses[path], meta: {} })); vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);
function show(page: ReactElement) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const inspection = (state: string, extra = {}) => ({ inspection_id: "INS-1", establishment_id: "EST-1", purpose: "COMPLAINT", period_from: "2025-04", period_to: "2025-09",
  state, due_at: "2026-10-05T10:00:00Z", overdue: false, report: null, steps: [], ...extra });
const report = { employees_found: 40, employees_not_enrolled: 12, findings: "12 workers not enrolled", dues_estimate_paise: 5000000, recommendation: "INITIATE_7A_DUES" };

it("lets the circle officer schedule an inspection and the EO report", async () => {
  as("fo.apfc"); responses["/api/v1/office/compliance/inspections"] = [];
  show(<InquiriesPage />);
  const form = await screen.findByRole("form", { name: "Schedule an inspection" });
  fireEvent.change(within(form).getByLabelText("Period from"), { target: { value: "2025-04" } });
  fireEvent.change(within(form).getByLabelText("Period to"), { target: { value: "2025-09" } });
  fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Complaint by workers" } });
  fireEvent.click(within(form).getByRole("button", { name: "Schedule" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/inspections", expect.objectContaining({ establishment_id: "EST-DEMO-0001", purpose: "COMPLAINT", period_from: "2025-04" })));
  cleanup(); as("fo.eo"); responses["/api/v1/office/compliance/inspections"] = [inspection("SCHEDULED")];
  show(<InquiriesPage />);
  const rep = await screen.findByRole("form", { name: "Report INS-1" });
  expect(screen.queryByRole("form", { name: "Schedule an inspection" })).toBeNull();
  for (const [label, value] of [["Visited on", "2026-10-01"], ["Employees found", "40"], ["Not enrolled", "12"], ["Monthly wages (₹)", "15000"], ["Dues estimated (₹)", "50000"], ["Findings", "Unenrolled"]])
    fireEvent.change(within(rep).getByLabelText(label), { target: { value } });
  fireEvent.click(within(rep).getByRole("button", { name: "Submit report" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/inspections/INS-1/reports", expect.objectContaining({ employees_found: 40, dues_estimate_paise: 5000000, wages_paise_monthly: 1500000 })));
});

it("routes the report through DA, SS and the circle officer's decision, then the SS registers the inquiry", async () => {
  as("fo.da_compliance"); responses["/api/v1/office/compliance/inspections"] = [inspection("REPORTED", { report })]; responses["/api/v1/office/compliance/cases"] = [];
  show(<InquiriesPage />);
  expect(await screen.findByText(/estimated dues ₹50,000/)).toBeTruthy();
  const da = screen.getByRole("form", { name: "Process INS-1" });
  expect(within(da).queryByLabelText("Decision")).toBeNull();
  cleanup(); as("fo.apfc"); responses["/api/v1/office/compliance/inspections"] = [inspection("SS_NOTED", { report })];
  show(<InquiriesPage />);
  const decide = await screen.findByRole("form", { name: "Process INS-1" });
  fireEvent.change(within(decide).getByLabelText("Note"), { target: { value: "Fit case" } });
  fireEvent.click(within(decide).getByRole("button", { name: "Record decision" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/inspections/INS-1/processing-notes", { note: "Fit case", decision: "INITIATE_7A" }));
  cleanup(); as("fo.ss"); responses["/api/v1/office/compliance/inspections"] = [inspection("DECIDED_INITIATE", { report })];
  show(<InquiriesPage />);
  const reg = await screen.findByRole("form", { name: "Register inquiry INS-1" });
  expect((within(reg).getByLabelText("Contributory UANs") as HTMLInputElement).value).toBe("40");
  fireEvent.change(within(reg).getByLabelText("Note"), { target: { value: "From the report" } });
  fireEvent.click(within(reg).getByRole("button", { name: "Register on e-Proceedings" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases", expect.objectContaining({ kind: "INQUIRY_7A", inspection_id: "INS-1", contributory_uans: 40 })));
});

it("lets the allotted officer pass the 7A order with a one-time code bound to the amount", async () => {
  as("fo.apfc"); responses["/api/v1/office/compliance/inspections"] = [];
  responses["/api/v1/office/compliance/cases"] = [{ case_id: "CMP-1", establishment_id: "EST-1", legal_name: "Synthetic Textiles", kind: "INQUIRY_7A", state: "OPEN" }];
  responses["/api/v1/office/compliance/cases/CMP-1"] = { case_id: "CMP-1", establishment_id: "EST-1", legal_name: "Synthetic Textiles", kind: "INQUIRY_7A", state: "OPEN",
    inquiry: { diary_no: "EPR/RO-DEMO-01/2026/0001", officer_rank: "APFC", officer_subject: "x", state: "CONCLUDED", period_from: "2025-04", period_to: "2025-09", contributory_uans: 40,
      order_due_at: "2026-10-23T10:00:00Z", actions: [{ kind: "SUMMONS", at: "2026-10-01T10:00:00Z", detail: { hearing_at: "2026-10-02T10:00:00Z" } },
        { kind: "HEARING", at: "2026-10-02T10:00:00Z", detail: { proceedings: "Arguments heard", employer_present: true } }] } };
  show(<InquiriesPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Open" }));
  const form = await screen.findByRole("form", { name: "Pass 7A order" });
  expect(screen.getByText(/EPR\/RO-DEMO-01\/2026\/0001/)).toBeTruthy();
  fireEvent.change(within(form).getByLabelText("Wage month"), { target: { value: "2025-04" } });
  fireEvent.change(within(form).getByLabelText("A/c 1 employee (₹)"), { target: { value: "21600" } });
  fireEvent.change(within(form).getByLabelText("A/c 10 pension (₹)"), { target: { value: "15000" } });
  fireEvent.change(within(form).getByLabelText("Findings and reasons"), { target: { value: "Muster roll" } });
  fireEvent.click(within(form).getByRole("button", { name: "Pass order" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "pass-order", resourceId: "CMP-1", amountPaise: 3660000 })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/compliance/cases/CMP-1/orders",
    expect.objectContaining({ kind: "7A", ex_parte: false, dues: [expect.objectContaining({ wage_month: "2025-04", ac1_employee_paise: 2160000, ac10_pension_paise: 1500000 })] }), { stepUpToken: "step-token" }));
});

it("shows the employer the summons, daily orders and a reply form, then the order", async () => {
  as("employer.owner");
  const base = { case_id: "CMP-1", diary_no: "EPR/RO-DEMO-01/2026/0001", dispute: "DUES", period_from: "2025-04", period_to: "2025-09", officer_rank: "APFC", state: "HEARING",
    summons: [{ kind: "SUMMONS", at: "x", detail: { hearing_at: "2026-10-02T10:00:00Z", meeting_link: "https://meet.example.invalid/CMP-1", case_status_url: "http://e", scope: "Dues" } }],
    daily_orders: [{ kind: "HEARING", at: "x", detail: { held_at: "2026-10-02T10:00:00Z", proceedings: "Employer asks for time", next_hearing_at: "2026-10-08T10:00:00Z" } }], submissions: [], order: null };
  responses["/api/v1/employers/me/proceedings"] = [base];
  show(<EmployerProceedingsPage />);
  expect(await screen.findByRole("link", { name: "join the hearing" })).toBeTruthy();
  expect(screen.getByText(/Employer asks for time/)).toBeTruthy();
  const reply = screen.getByRole("form", { name: "Reply in EPR/RO-DEMO-01/2026/0001" });
  fireEvent.change(within(reply).getByLabelText("Text"), { target: { value: "Contract workers" } });
  fireEvent.change(within(reply).getByLabelText(/Documents/), { target: { value: "a.pdf, b.pdf" } });
  fireEvent.click(within(reply).getByRole("button", { name: "Submit" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/employers/me/proceedings/CMP-1/submissions", { kind: "REPLY", text: "Contract workers", documents: ["a.pdf", "b.pdf"] }));
  cleanup(); responses["/api/v1/employers/me/proceedings"] = [{ ...base, state: "ORDERED", order: { kind: "ORDER", at: "x", detail: { total_paise: 4500000, ex_parte: false, demand_id: "D7A-CMP-1", text: "ORDER UNDER SECTION 7A" } } }];
  show(<EmployerProceedingsPage />);
  expect(await screen.findByText("₹45,000.00")).toBeTruthy();
  expect(screen.queryByRole("form", { name: /Reply in/ })).toBeNull();
});

it("links the screens from the menus", () => {
  for (const role of ["fo.apfc", "fo.ss", "fo.eo", "fo.oic", "fo.da_compliance"])
    expect(menusFor(role).flatMap((g) => g.items ?? [])).toContainEqual(expect.objectContaining({ label: "Inspections and 7A inquiries", to: "/office/inquiries" }));
  expect(menusFor("employer.owner").flatMap((g) => g.items ?? [])).toContainEqual(expect.objectContaining({ label: "Inquiries (e-Proceedings)", to: "/employer/proceedings" }));
  expect(homeFor("fo.eo")).toBe("/office/inquiries");
});
