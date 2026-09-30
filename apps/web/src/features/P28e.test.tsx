import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { ApiError, api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { SecurityActivity } from "../pages/SecurityActivity";
import { ConcurrentAuditPage } from "./audit/ConcurrentAuditPage";
import { EmployerDashboard } from "./employer/EmployerDashboard";
import { MemberLocations } from "./employer/MemberLocations";
import { HrmPage } from "./hrm/HrmPage";
import { IssueTrackerPage, IssueTrackerRequests } from "./ndc/IssueTrackerPage";
import { DistrictDashboardPage } from "./office/DistrictDashboardPage";
import { FraudRiskPage } from "./office/FraudRiskPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(),
}));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const uan = "100000000001";
const incident = { incident_id: "INC-1", title: "Unauthorised login", category: "UNAUTHORISED_ACCESS", severity: "HIGH", detected_at: "2026-09-01T10:30:00Z",
  description: "Unauthorised access was detected in the portal.", affected_systems: ["Portal", "Gateway"], related_event_ids: ["EV-1", "EV-2"], recorded_at: "2026-09-01T11:00:00Z",
  cert_in: { required: true, due_by: "2026-09-01T16:30:00Z", reported_at: "2026-09-01T11:00:00Z", late: false, acknowledgement: "CERTIN-MOCK-1" }, note: "Reported to CERT-In (mock)." };
const request = { request_id: "ITR-1", kind: "FREEZE_MEMBER", target_uan: uan, order_ref: "ORDER-1", order_document: null,
  reason: "Review the account under this order.", notice: null, state: "RAISED", raised_role: "fo.oic", raised_at: "2026-09-01", executed_at: null, execution_note: null };
const posting = { username: "office-oic", stakeholder: "fo.oic", office_id: "RO-2", previous: { stakeholder: "fo.apfc", office_id: "RO-1" }, note: "Previous assignments released." };
const item = { event_id: "EV-1", occurred_at: "2026-09-01", event_type: "ClaimSettled.v1", reference: "CLM-1", amount_paise: 123456,
  office_id: null, flags: ["LARGE_AMOUNT"], correlation_id: "COR-1", hash: "hash-1" };
const alert = { alert_id: "CAA-1", office_id: "RO-DEMO-01", zone_id: "ZO-1", reference: "CLM-1", event_id: "EV-1", flags: ["LARGE_AMOUNT"],
  finding: "Review this settlement.", state: "OPEN", due_by: "2026-09-04", raised_at: "2026-09-01", reply: null, overdue: true };
let responses: Record<string, unknown>; let clients: QueryClient[];

beforeEach(() => {
  vi.clearAllMocks(); clients = [];
  responses = {
    "/api/v1/security/request-activity": { window_seconds: 300, retention_seconds: 86400, history_limit: 10, gateway_peer_note: "Demo activity.",
      metrics: { requests_5m: 0, requests_1m: 0, blocked_5m: 0, challenge_failures_5m: 0, server_errors_5m: 0 }, top_routes: [], top_peers: [], events: [] },
    "/api/v1/security/incidents": [],
    "/api/v1/ndc/issue-tracker/requests": [request],
    "/api/v1/hrm/me": { username: "hrm-employee", role: "ho.hr", office: { office_id: "HO-1", name: "Head office" } },
    "/api/v1/public/offices": [{ office_id: "RO-1", name: "Current office" }, { office_id: "RO-2", name: "Receiving office" }],
    "/api/v1/audit/concurrent/alerts": [alert],
    "/api/v1/employers/me/members": [{ uan, name: "Demo Member", account_link_id: "AL-1", status: "ACTIVE", location: { branch_code: "BR-1", district: "DELHI", pincode: "110001" } }],
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.startsWith("/api/v1/audit/concurrent/extracts?")) return { data: { day: path.split("=")[1], items: [item], flag_counts: { LARGE_AMOUNT: 1 }, events_scanned: 12, note: "Illustrative red flags." }, meta: {} };
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockImplementation(async (_method, path) => ({ data: path === "/api/v1/security/incidents" ? incident
    : path === "/api/v1/hrm/postings" ? posting : path.includes("location-mappings") ? { uan, account_link_id: "AL-1", location: { branch_code: "BR-2", district: "DELHI", pincode: "110002" } }
    : path === "/api/v1/audit/concurrent/alerts" ? alert : request, meta: {} }));
  ask.mockResolvedValue("step-up-token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });
function renderPage(page: ReactElement, role = "ho.security") {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client); render(<QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>);
}
function fill(form: HTMLElement, label: string, value: string) { fireEvent.change(within(form).getByLabelText(label), { target: { value } }); }
async function incidentForm() {
  renderPage(<SecurityActivity />);
  const form = await screen.findByRole("form", { name: "Record a security incident" });
  fill(form, "Title", incident.title); fill(form, "Category", incident.category); fill(form, "Severity", incident.severity);
  fill(form, "Detected at (local time)", "2026-09-01T10:30"); fill(form, "Description", incident.description);
  fill(form, "Affected systems (comma separated)", " Portal, Gateway, "); fill(form, "Related event IDs (comma separated)", "EV-1, EV-2,");
  return form;
}
async function executionForm() {
  renderPage(<IssueTrackerPage />, "ho.is");
  const form = await screen.findByRole("form", { name: "Decide request ITR-1" });
  fill(form, "Decision", "EXECUTE"); fill(form, "Decision note", "Order checked and approved."); return form;
}
async function postingForm() {
  renderPage(<HrmPage />, "ho.hr");
  const form = await screen.findByRole("form", { name: "Post staff" });
  await within(form).findByRole("option", { name: /Receiving office/ });
  fill(form, "Username", posting.username); fill(form, "Stakeholder role", posting.stakeholder); fill(form, "Office", "RO-2");
  fill(form, "Posting reason", "Transfer approved for office coverage."); return form;
}
const forms = { incident: incidentForm, execution: executionForm, posting: postingForm };

it("binds incident confirmation to category and severity, converts local time and comma lists, and displays CERT-In details", async () => {
  fireEvent.submit(await incidentForm());
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/security/incidents", {
    title: incident.title, category: incident.category, severity: incident.severity, detected_at: new Date("2026-09-01T10:30").toISOString(),
    description: incident.description, affected_systems: incident.affected_systems, related_event_ids: incident.related_event_ids,
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "record-security-incident", resourceId: "UNAUTHORISED_ACCESS:HIGH", summary: expect.any(String) });
  expect(await screen.findByText(incident.note)).toBeTruthy(); expect(screen.getByText("CERTIN-MOCK-1")).toBeTruthy();
  expect(screen.getByText(incident.cert_in.due_by)).toBeTruthy();
});
it.each(["EXECUTE", "REJECT"])("binds Issue Tracker %s to the request ID", async (decision) => {
  const form = await executionForm(); fill(form, "Decision", decision); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/ndc/issue-tracker/requests/ITR-1/executions",
    { decision, note: "Order checked and approved." }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "execute-issue-tracker", resourceId: "ITR-1", summary: expect.any(String) });
});
it("binds a staff posting to the username and displays its previous posting", async () => {
  fireEvent.submit(await postingForm());
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/hrm/postings", {
    username: "office-oic", stakeholder: "fo.oic", office_id: "RO-2", reason: "Transfer approved for office coverage.",
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "post-staff", resourceId: "office-oic", summary: expect.any(String) });
  expect(await screen.findByText("Previous posting: fo.apfc · RO-1")).toBeTruthy(); expect(screen.getByText(posting.note)).toBeTruthy();
});
it("accepts an explicit ZO- ID for a zonal staff posting", async () => {
  const form = await postingForm(); fill(form, "Stakeholder role", "zo.rpfc1_audit"); fill(form, "Zonal office ID (optional)", "ZO-DEMO-02"); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/hrm/postings", expect.objectContaining({ office_id: "ZO-DEMO-02", stakeholder: "zo.rpfc1_audit" }), { stepUpToken: "step-up-token" }));
});
it.each(["incident", "execution", "posting"] as const)("does not send %s if step-up is cancelled", async (kind) => {
  ask.mockResolvedValue(null); fireEvent.submit(await forms[kind]());
  await waitFor(() => expect(ask).toHaveBeenCalled()); expect(command).not.toHaveBeenCalled();
});
it.each(["incident", "execution", "posting"] as const)("freezes %s inputs and waits for confirmation before sending", async (kind) => {
  let confirm!: (token: string | null) => void; ask.mockImplementation(() => new Promise((resolve) => { confirm = resolve; }));
  const form = await forms[kind](); fireEvent.submit(form); await waitFor(() => expect(ask).toHaveBeenCalled());
  expect((within(form).getByRole("group") as HTMLFieldSetElement).disabled).toBe(true); expect(command).not.toHaveBeenCalled();
  await act(async () => confirm(null));
  expect((within(form).getByRole("group") as HTMLFieldSetElement).disabled).toBe(false);
});
it.each(["incident", "execution", "posting"] as const)("validates the %s description or note before step-up", async (kind) => {
  const form = await forms[kind](); fill(form, kind === "incident" ? "Description" : kind === "execution" ? "Decision note" : "Posting reason", "bad"); fireEvent.submit(form);
  expect(await screen.findByRole("alert")).toBeTruthy(); expect(ask).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
});
it.each(["incident", "execution", "posting"] as const)("shows service validation problems for %s", async (kind) => {
  vi.mocked(command).mockRejectedValue(new ApiError({ type: "/problems/validation", status: 422, title: "Review the record", detail: "The record could not be accepted.", errors: [{ field: "reason", message: "Please check." }] }));
  fireEvent.submit(await forms[kind]()); expect(await screen.findByText("The record could not be accepted.")).toBeTruthy(); expect(screen.getByText("reason: Please check.")).toBeTruthy();
});
it.each(["security", "is", "hr"])("does not load %s data or offer its sensitive forms to another role", async (kind) => {
  renderPage(kind === "security" ? <SecurityActivity /> : kind === "is" ? <IssueTrackerPage /> : <HrmPage />, "member");
  await waitFor(() => expect(getSession).toHaveBeenCalled()); await screen.findByText(kind === "security" ? "Security role required" : kind === "is" ? "This service is available to the IS Division." : "This service is available to HR.");
  expect(api).not.toHaveBeenCalled(); expect(screen.queryByRole("form")).toBeNull();
});
it("shows completed Issue Tracker requests without a decision form", async () => {
  responses["/api/v1/ndc/issue-tracker/requests"] = [{ ...request, state: "EXECUTED", execution_note: "Completed.", executed_at: "2026-09-02" }];
  renderPage(<IssueTrackerPage />, "ho.is"); expect(await screen.findByText("Completed.")).toBeTruthy(); expect(screen.queryByRole("form")).toBeNull();
});
it("selects an audit day, displays rupees and raises an event-bound alert", async () => {
  renderPage(<ConcurrentAuditPage />, "zo.rpfc1_audit");
  fireEvent.change(await screen.findByLabelText("Extract day"), { target: { value: "2026-09-01" } });
  await waitFor(() => expect(api).toHaveBeenCalledWith("/api/v1/audit/concurrent/extracts?day=2026-09-01"));
  const form = await screen.findByRole("form", { name: "Raise alert for EV-1" }); expect(screen.getByText("₹1,234.56")).toBeTruthy();
  fill(form, "Finding", "Please review this settlement."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/audit/concurrent/alerts", {
    office_id: "RO-DEMO-01", reference: "CLM-1", event_id: "EV-1", flags: ["LARGE_AMOUNT"], finding: "Please review this settlement.",
  })); expect(ask).not.toHaveBeenCalled();
});
it("lets the OIC reply to open alerts, without loading auditor extracts", async () => {
  responses["/api/v1/audit/concurrent/alerts"] = [alert, { ...alert, alert_id: "CAA-2", state: "REPLIED", reply: { reply: "Already answered.", action_taken: "Checked records.", by: "office-oic", at: "2026-09-02", late: true } }];
  renderPage(<ConcurrentAuditPage />, "fo.oic"); const form = await screen.findByRole("form", { name: "Reply to alert CAA-1" });
  expect(screen.queryByRole("form", { name: "Reply to alert CAA-2" })).toBeNull(); expect(screen.getByText("Already answered.")).toBeTruthy();
  fill(form, "Reply", "The settlement was checked."); fill(form, "Action taken", "Records verified."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/audit/concurrent/alerts/CAA-1/replies", { reply: "The settlement was checked.", action_taken: "Records verified." }));
  expect(api).not.toHaveBeenCalledWith(expect.stringContaining("extracts")); expect(ask).not.toHaveBeenCalled();
});
it("raises a login notice request from the OIC page", async () => {
  renderPage(<ConcurrentAuditPage />, "fo.oic"); const form = await screen.findByRole("form", { name: "Raise an Issue Tracker request" });
  fill(form, "Request kind", "LOGIN_NOTICE"); fill(form, "Target UAN", uan); fill(form, "Order reference", "ORDER-2"); fill(form, "Reason", "The member needs to review the order."); fill(form, "Login notice", "Please contact your office."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/ndc/issue-tracker/requests", { kind: "LOGIN_NOTICE", target_uan: uan, order_ref: "ORDER-2", reason: "The member needs to review the order.", notice: "Please contact your office." })); expect(ask).not.toHaveBeenCalled();
});
it("attaches a PDF order as base64 without a data URL prefix", async () => {
  renderPage(<IssueTrackerRequests />, "fo.oic"); const form = screen.getByRole("form", { name: "Raise an Issue Tracker request" });
  fill(form, "Target UAN", uan); fill(form, "Order reference", "ORDER-1"); fill(form, "Reason", request.reason);
  const file = new File(["%PDF-1.4\nDemo order"], "order.pdf", { type: "application/pdf" });
  fireEvent.change(within(form).getByLabelText("Order PDF (optional, up to 2 MB)"), { target: { files: [file] } });
  // jsdom's FormData does not copy a synthetic file input's FileList.
  const original = globalThis.FormData;
  const spy = vi.spyOn(globalThis, "FormData").mockImplementation((element) => { const data = new original(element); data.set("order", file); return data; });
  try {
    fireEvent.submit(form);
    await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/ndc/issue-tracker/requests", {
      kind: "FREEZE_MEMBER", target_uan: uan, order_ref: "ORDER-1", reason: request.reason, order_filename: "order.pdf", order_base64: btoa("%PDF-1.4\nDemo order"),
    }));
  } finally { spy.mockRestore(); }
});
it("maps a member location and renders the member's existing location", async () => {
  renderPage(<MemberLocations canMap />, "employer.operator"); const form = screen.getByRole("form", { name: "Map member location" });
  expect(await screen.findByText("BR-1 · DELHI · 110001")).toBeTruthy(); fill(form, "UAN", uan); fill(form, "Member ID at this establishment", "AL-1"); fill(form, "Branch code", "BR-2"); fill(form, "District", "DELHI"); fill(form, "Pincode", "110002"); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `/api/v1/employers/me/members/${uan}/location-mappings`, { account_link_id: "AL-1", branch_code: "BR-2", district: "DELHI", pincode: "110002" }));
});
it("shows district metrics and explains a null SLA percentage", async () => {
  responses["/api/v1/do/dashboards"] = { office_id: "DO-1", as_of: "2026-09-01", claims: { pending: 8, settled_last_30_days: 12, pending_over_sla: 3, returned_payments: 1 },
    grievances: { open: 4, resolved_last_30_days: 2, resolved_within_sla_pct: null, escalated_open: 1 }, establishments: { with_filings: 20, defaulting: 5, paid_late_last_12_months: 6 }, note: "Synthetic district data." };
  renderPage(<DistrictDashboardPage />, "do.incharge"); expect(await screen.findByText("fewer than 5 resolved")).toBeTruthy();
  const metrics = screen.getByRole("region", { name: "District metrics" }); expect(within(metrics).getByText("Pending claims")).toBeTruthy(); expect(within(metrics).getByText("8")).toBeTruthy(); expect(screen.getByText("Synthetic district data.")).toBeTruthy();
});
it("displays employer alerts and related services as links", async () => {
  responses["/api/v1/employers/me/dashboard"] = { establishment_id: "EST-1", as_of: "2026-09-01", returns: [{ wage_month: "2026-08", status: "NOT_FILED", due_date: "2026-09-15", paid_on: null }], alerts: [{ kind: "RETURN_DUE", message: "File the return", link: "/employer/ecr" }], counts: { NOT_FILED: 1 }, see_also: [{ label: "Compliance summary", link: "/employer/returns" }], note: "Synthetic filing data." };
  renderPage(<EmployerDashboard />, "employer.operator"); expect((await screen.findByRole("link", { name: "File the return" })).getAttribute("href")).toBe("/employer/ecr");
  expect(screen.getByRole("link", { name: "Compliance summary" }).getAttribute("href")).toBe("/employer/returns"); expect(screen.getByText("2026-08")).toBeTruthy();
});
it("displays the committee's zone, case details and advisory note", async () => {
  responses["/api/v1/zo/fraud-risk/cases"] = { zone_id: "ZO-1", cases: [{ case_id: "CASE-1", kind: "CLAIM", process: "claim", office_id: "RO-1", office: "Demo office", subject_ref: uan, claim_id: "CLM-1", state: "OPEN", advisory_signal_id: "RISK-1", why: "Advisory risk signal on the claim", opened_at: "2026-09-01" }], note: "Illustrative selection." };
  renderPage(<FraudRiskPage />, "zo.fraud_committee"); expect(await screen.findByText("RISK-1")).toBeTruthy(); expect(screen.getByText("Zone ZO-1")).toBeTruthy(); expect(screen.getByText("Illustrative selection.")).toBeTruthy();
});
it.each([["zo.rpfc1_audit", "/audit/concurrent"], ["ho.is", "/ndc/issue-tracker"], ["zo.fraud_committee", "/zo/fraud-risk"], ["do.incharge", "/do/dashboard"], ["ho.hr", "/i/hrm"]])("links %s to its workspace", (role, path) => {
  expect(homeFor(role)).toBe(path); expect(menusFor(role).some((group) => group.to === path)).toBe(true);
});
it("links employer location mapping and the OIC's two oversight sections", () => {
  const employer = menusFor("employer.operator").flatMap((group) => group.items ?? []); expect(employer).toContainEqual(expect.objectContaining({ label: "Member Location Mapping", to: "/employer/members#location-heading" }));
  const oic = menusFor("fo.oic").flatMap((group) => group.items ?? []); expect(oic).toContainEqual(expect.objectContaining({ to: "/audit/concurrent#audit-alerts-heading" })); expect(oic).toContainEqual(expect.objectContaining({ to: "/audit/concurrent#issue-tracker-raise-heading" }));
});
