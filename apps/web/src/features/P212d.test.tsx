import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { ConcurrentAuditPage } from "./audit/ConcurrentAuditPage";
import { InternalAuditPage } from "./audit/InternalAuditPage";
import { InternalParas } from "./audit/InternalParas";
import { PrivacyRequestsPage } from "./audit/PrivacyRequestsPage";
import { RtiApplications } from "./grievance/RtiApplications";
import { PrivacyRequests } from "./member/PrivacyRequests";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const para = { para_id: "PAR-1", report_id: "IAR-1", office_id: "RO-1", category: "CLAIMS", observation: "A claim needs a documented audit review.",
  recommendation: "Correct the record.", amount_at_risk_paise: 12345, reply_due: "2026-10-04", state: "OPEN", overdue: false, replies: [] };
const privacy = { request_id: "DPR-1", kind: "ACCESS", details: "Please provide my personal data.", state: "OPEN", due_on: "2026-10-10", answer: null,
  member_reference: "****1234", overdue: true };
const rti = { request_id: "RTI-1", registration_no: "RTI/RO-1/2026/1", subject: "Request about pension records", state: "OPEN", outcome: null,
  reply_due: "2026-10-10", days_left: 9, overdue: false };
let responses: Record<string, unknown>; let clients: QueryClient[];
beforeEach(() => {
  vi.clearAllMocks(); clients = [];
  responses = { "/api/v1/audit/internal/paras": [para], "/api/v1/privacy/requests": [privacy],
    "/api/v1/members/me/privacy-requests": [privacy], "/api/v1/office/rti-requests": [rti],
    "/api/v1/audit/concurrent/alerts": [], "/api/v1/ndc/issue-tracker/requests": [] };
  vi.mocked(api).mockImplementation(async (path) => {
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockImplementation(async (_method, path) => ({ data: path === "/api/v1/audit/internal/reports" ? { report_id: "IAR-1" }
    : path === "/api/v1/office/rti-requests" ? { registration_no: rti.registration_no } : {}, meta: {} }));
  ask.mockResolvedValue("step-up-token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });
function page(element: ReactElement, role = "member") {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>);
}
function fill(form: HTMLElement, label: string, value: string) { fireEvent.change(within(form).getByLabelText(label), { target: { value } }); }

it("creates an internal report and posts a para with rupees converted to paise", async () => {
  page(<InternalAuditPage />, "zo.internal_audit"); const report = screen.getByRole("form", { name: "Create internal audit report" });
  fill(report, "Office ID", "RO-1"); fill(report, "Period from", "2026-09-01"); fill(report, "Period to", "2026-09-30");
  fill(report, "Scope", "Review of pension and claims activity."); fireEvent.submit(report);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/audit/internal/reports", {
    office_id: "RO-1", period_from: "2026-09-01", period_to: "2026-09-30", scope: "Review of pension and claims activity." }));
  const form = await screen.findByRole("form", { name: "Add para to IAR-1" });
  fill(form, "Category", "PENSION"); fill(form, "Observation", "Pension amount requires a fresh review.");
  fill(form, "Amount at risk (₹)", "123.45"); fill(form, "References (comma-separated)", " CLM-1, PAY-2, "); fill(form, "Recommendation", "Correct the payment."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/audit/internal/reports/IAR-1/paras", {
    category: "PENSION", observation: "Pension amount requires a fresh review.", amount_at_risk_paise: 12345,
    references: ["CLM-1", "PAY-2"], recommendation: "Correct the payment." }));
});

it("lets the OIC reply to its para", async () => {
  page(<InternalParas role="fo.oic" />, "fo.oic"); const form = await screen.findByRole("form", { name: "Reply to para PAR-1" });
  fill(form, "Reply", "The claim was checked against office records."); fill(form, "Action taken", "Record corrected.");
  fireEvent.click(within(form).getByLabelText("Request drop")); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/audit/internal/paras/PAR-1/replies", {
    reply: "The claim was checked against office records.", action_taken: "Record corrected.", request_drop: true }, {}));
});

it("uses step-up for an Audit Division para decision", async () => {
  responses["/api/v1/audit/internal/paras"] = [{ ...para, state: "REPLIED", replies: [{ reply: "The office reviewed this claim.", action_taken: "Corrected." }] }];
  page(<InternalParas role="ho.audit" />, "ho.audit"); const form = await screen.findByRole("form", { name: "Decide para PAR-1" });
  fill(form, "Decision", "KEEP"); fill(form, "Decision note", "Further evidence is needed."); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "decide-audit-para", resourceId: "PAR-1" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/audit/internal/paras/PAR-1/decisions", { decision: "KEEP", note: "Further evidence is needed." }, { stepUpToken: "step-up-token" }));
});

it("submits and lists the member's personal data requests", async () => {
  page(<PrivacyRequests />); expect(await screen.findByText(/Please provide my personal data/)).toBeTruthy();
  const form = screen.getByRole("form", { name: "Request about your personal data" }); fill(form, "Request type", "CORRECTION");
  fill(form, "Details", "Please correct my recorded address."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/members/me/privacy-requests", { kind: "CORRECTION", details: "Please correct my recorded address." }));
});

it("requires legal basis before a rejected DPO decision and sends step-up", async () => {
  page(<PrivacyRequestsPage />, "ho.data_protection"); const form = await screen.findByRole("form", { name: "Decide request DPR-1" });
  fill(form, "Decision", "REJECTED"); fill(form, "Answer", "The request cannot be granted as described."); fireEvent.submit(form);
  expect(command).not.toHaveBeenCalled(); expect(ask).not.toHaveBeenCalled();
  fill(form, "Legal basis", "Applicable retention obligation."); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "decide-privacy-request", resourceId: "DPR-1" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/privacy/requests/DPR-1/decisions", {
    decision: "REJECTED", answer: "The request cannot be granted as described.", legal_basis: "Applicable retention obligation." }, { stepUpToken: "step-up-token" }));
});

it("registers RTI and requires an exemption for refusal before replying", async () => {
  page(<RtiApplications />, "fo.pro"); const register = screen.getByRole("form", { name: "Register RTI application" });
  fill(register, "Applicant", "Asha Kumar"); fill(register, "Received on", "2026-09-30"); fill(register, "Mode", "COUNTER");
  fill(register, "Subject", "Pension record enquiry"); fill(register, "Information sought", "Please provide the pension record details.");
  fireEvent.click(within(register).getByLabelText("Fee paid")); fireEvent.submit(register);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/rti-requests", {
    applicant_name: "Asha Kumar", received_on: "2026-09-30", mode: "COUNTER", subject: "Pension record enquiry",
    information_sought: "Please provide the pension record details.", fee_paid: true, bpl: false }));
  const reply = await screen.findByRole("form", { name: `Reply to RTI ${rti.registration_no}` });
  fill(reply, "Outcome", "REFUSED"); fill(reply, "Reply", "The requested record is exempt from disclosure."); fireEvent.submit(reply);
  expect(command).toHaveBeenCalledTimes(1); fill(reply, "Exemption section", "8(1)(j)"); fireEvent.submit(reply);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/rti-requests/RTI-1/replies", {
    outcome: "REFUSED", reply: "The requested record is exempt from disclosure.", exemption_section: "8(1)(j)", transferred_to: null }));
});

it("routes both new roles to their pages and includes their menu links", () => {
  expect(homeFor("zo.internal_audit")).toBe("/audit/internal"); expect(homeFor("ho.data_protection")).toBe("/privacy");
  expect(menusFor("zo.internal_audit")).toContainEqual({ label: "Internal audit", to: "/audit/internal" });
  expect(menusFor("ho.data_protection")).toContainEqual({ label: "Data-principal requests", to: "/privacy" });
});

it("keeps the OIC para section on concurrent audit", async () => {
  page(<ConcurrentAuditPage />, "fo.oic"); expect(await screen.findByRole("heading", { name: "Internal-audit paras" })).toBeTruthy();
});
