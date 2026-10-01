import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { ApiError, api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { HrmPage } from "./hrm/HrmPage";
import { RiskSignalsPage } from "./oversight/RiskSignalsPage";
import { VigilancePage } from "./vigilance/VigilancePage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(),
}));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const summary = { case_id: "VC-1", vcn: "VIG/2026/0001", source: "CAIU_SIGNAL", source_ref: "SIG-1",
  subject_type: "MEMBER", subject_ref: "100000000001", office_id: "RO-DEMO-01", zone_id: "ZO-1",
  state: "REFERRED", outcome: null, pi_due: null, opened_at: "2026-09-01", complainant: { name: "Asha Rao", contact: "asha@example.org" }, overdue: false };
const detail = { ...summary, allegation: "The payment appears to have been redirected improperly.",
  evidence: [{ kind: "RISK_SIGNAL", ref: "SIG-1" }], findings: null,
  history: [{ actor: "ho.caiu", action: "REFERRED", note: null, at: "2026-09-01" }] };
const signal = { signal_id: "SIG-1", subject_ref: "100000000001", detection_type: "PAYMENT_PATTERN", rule_version: "v1",
  evidence_refs: ["EV-1"], explanation: "Repeated payment changes.", context: {}, status: "CONFIRMED",
  review_note: "Confirmed after manual review.", reviewed_at: "2026-09-01", created_at: "2026-09-01", advisory_only: true };
let responses: Record<string, unknown>;
let clients: QueryClient[];

beforeEach(() => {
  vi.clearAllMocks(); clients = [];
  responses = {
    "/api/v1/vigilance/cases": { zone_id: null, cases: [summary], restricted: true, note: "Restricted" },
    "/api/v1/vigilance/cases/VC-1": detail,
    "/api/v1/vigilance/sensitive-posts": { officers: [{ username: "officer.one", stakeholder: "fo.oic", office_id: "RO-DEMO-01", posted_since: "2023-01-01", tenure_months: 44, rotation: "ROTATION_OVERDUE" }], transfer_list: ["officer.one"] },
    "/api/v1/vigilance/clearances": { clearances: [{ clearance_id: "VCL-1", username: "officer.one", purpose: "POSTING_SENSITIVE", cleared: false, valid_until: "2026-12-01", issued_at: "2026-10-01", reason: "A vigilance matter is pending.", case_ids: ["VC-1"] }] },
    "/api/v1/hrm/me": { username: "hr.one", role: "ho.hr", office: { office_id: "HO", name: "Head office" } },
    "/api/v1/public/offices": [{ office_id: "RO-DEMO-01", name: "Demo office" }],
    "/api/v1/caiu/synthetic-risk-signals": { rule_version: "v1", signals: [signal], shared_devices_not_signals: [] },
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockResolvedValue({ data: { vcn: "VIG/2026/0002" }, meta: {} });
  ask.mockResolvedValue("step-up-token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });

function renderPage(page: ReactElement, role: string, url = "/vigilance?case=VC-1") {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>{page}</MemoryRouter></QueryClientProvider>);
}

it("shows the CVO list, complainant, and only the referral decisions", async () => {
  renderPage(<VigilancePage />, "ho.cvo");
  expect(await screen.findByRole("heading", { name: "VIG/2026/0001" })).toBeTruthy();
  expect(screen.getByText("Asha Rao · asha@example.org")).toBeTruthy();
  const table = within(screen.getByRole("region", { name: "Cases" })).getByRole("table");
  expect(within(table).getByText("Referred")).toBeTruthy();
  const decision = screen.getByLabelText("Decision") as HTMLSelectElement;
  expect([...decision.options].map((option) => option.value)).toEqual(["", "ASSIGN_INQUIRY", "CLOSED_NO_SUBSTANCE"]);
  fireEvent.change(decision, { target: { value: "ASSIGN_INQUIRY" } });
  fireEvent.change(screen.getByLabelText("Decision note"), { target: { value: "Assign for preliminary inquiry." } });
  fireEvent.submit(screen.getByRole("form", { name: "Record vigilance decision" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/vigilance/cases/VC-1/decisions",
    { decision: "ASSIGN_INQUIRY", note: "Assign for preliminary inquiry." }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "decide-vigilance-case", resourceId: "VC-1" }));
});

it("masks the zone complainant and reports findings for an assigned inquiry", async () => {
  const assigned = { ...summary, state: "PI_ASSIGNED", pi_due: "2026-09-01", overdue: true, complainant: { masked: true } };
  responses["/api/v1/vigilance/cases"] = { zone_id: "ZO-1", cases: [assigned], restricted: true, note: "Restricted" };
  responses["/api/v1/vigilance/cases/VC-1"] = { ...detail, ...assigned };
  renderPage(<VigilancePage />, "zo.vigilance");
  expect(await screen.findByText("Masked — known to the CVO only")).toBeTruthy();
  expect(screen.queryByText(/Asha Rao/)).toBeNull();
  expect(within(screen.getByRole("table")).getByText("Overdue")).toBeTruthy();
  const form = screen.getByRole("form", { name: "Report vigilance findings" });
  fireEvent.click(within(form).getByLabelText("Substantiated"));
  fireEvent.change(within(form).getByLabelText("Report"), { target: { value: "The inquiry reviewed the audit trail and confirmed the payment diversion." } });
  fireEvent.change(within(form).getByLabelText("Recommendation"), { target: { value: "Begin proceedings." } });
  fireEvent.click(within(form).getByLabelText("RISK SIGNAL · SIG-1"));
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/vigilance/cases/VC-1/findings",
    { finding: "SUBSTANTIATED", report: "The inquiry reviewed the audit trail and confirmed the payment diversion.",
      recommendation: "Begin proceedings.", evidence_examined: ["SIG-1"] }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "report-vigilance-findings", resourceId: "VC-1" }));
  expect(api).not.toHaveBeenCalledWith("/api/v1/vigilance/sensitive-posts");
  expect(api).not.toHaveBeenCalledWith("/api/v1/vigilance/clearances");
});

it("shows CVO rotation and withholding cases", async () => {
  renderPage(<VigilancePage />, "ho.cvo");
  const posts = await screen.findByRole("region", { name: "Sensitive posts and rotation" });
  expect(within(posts).getByText("Overdue for rotation").className).toContain("vigilance-alert-pill");
  expect(within(posts).getByText("Due or overdue for the annual general transfer: officer.one")).toBeTruthy();
  const clearances = screen.getByRole("region", { name: "Vigilance clearances" });
  expect((await within(clearances).findByRole("link", { name: "VC-1" })).getAttribute("href")).toBe("/vigilance?case=VC-1");
});

it("lets HR request a clearance and shows a withheld result", async () => {
  vi.mocked(command).mockResolvedValueOnce({ data: { clearance_id: "VCL-2", username: "officer.one", purpose: "POSTING_SENSITIVE", cleared: false, valid_until: "2026-12-01", issued_at: "2026-10-01", reason: "A vigilance matter is pending." }, meta: {} });
  renderPage(<HrmPage />, "ho.hr", "/hrm");
  const clearance = await screen.findByRole("region", { name: "Vigilance clearance" });
  const form = within(clearance).getByRole("form", { name: "Issue vigilance clearance" });
  fireEvent.change(within(form).getByLabelText("Officer user name"), { target: { value: "officer.one" } });
  fireEvent.change(within(form).getByLabelText("Purpose"), { target: { value: "POSTING_SENSITIVE" } });
  fireEvent.change(within(form).getByLabelText("Note (optional)"), { target: { value: "Check for transfer." } });
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/vigilance/clearances", { username: "officer.one", purpose: "POSTING_SENSITIVE", note: "Check for transfer." }));
  expect(await within(clearance).findByText("Withheld — A vigilance matter is pending.")).toBeTruthy();
  expect(within(clearance).queryByRole("link", { name: "VC-1" })).toBeNull();
  const posts = screen.getByRole("region", { name: "Sensitive posts" });
  expect(within(posts).getByText("Overdue for rotation").className).toContain("vigilance-alert-pill");
});

it("shows the clearance needed problem on a sensitive posting", async () => {
  vi.mocked(command).mockRejectedValueOnce(new ApiError({ type: "/problems/vigilance-clearance-needed", title: "Vigilance clearance needed", status: 409, detail: "Request a current clearance before posting this officer." }));
  renderPage(<HrmPage />, "ho.hr", "/hrm");
  const form = await screen.findByRole("form", { name: "Post staff" });
  fireEvent.change(within(form).getByLabelText("Username"), { target: { value: "officer.one" } });
  fireEvent.change(within(form).getByLabelText("Stakeholder role"), { target: { value: "fo.oic" } });
  fireEvent.change(within(form).getByLabelText("Office"), { target: { value: "RO-DEMO-01" } });
  fireEvent.change(within(form).getByLabelText("Posting reason"), { target: { value: "Annual general transfer." } });
  fireEvent.submit(form);
  expect(await screen.findByText("Vigilance clearance needed")).toBeTruthy();
  expect(screen.getByText("Request a current clearance before posting this officer.")).toBeTruthy();
});

it("does not request case data for another role", async () => {
  renderPage(<VigilancePage />, "member");
  expect(await screen.findByText("This screen is for the Chief Vigilance Officer and zonal vigilance.")).toBeTruthy();
  expect(api).not.toHaveBeenCalled();
});

it("offers referral only for a confirmed signal and sends its evidence reference", async () => {
  responses["/api/v1/caiu/synthetic-risk-signals"] = { rule_version: "v1", signals: [signal, { ...signal, signal_id: "SIG-2", status: "BENIGN" }], shared_devices_not_signals: [] };
  renderPage(<RiskSignalsPage />, "ho.caiu", "/caiu/signals");
  const button = await screen.findByRole("button", { name: "Refer to vigilance" });
  expect(screen.getAllByRole("button", { name: "Refer to vigilance" })).toHaveLength(1);
  fireEvent.click(button);
  const form = screen.getByRole("form", { name: "Refer signal SIG-1 to vigilance" });
  fireEvent.change(within(form).getByLabelText("Allegation"), { target: { value: "The account may have been used for an improper payment." } });
  fireEvent.change(within(form).getByLabelText("Complainant name (optional)"), { target: { value: "Asha Rao" } });
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/vigilance/referrals", {
    source: "CAIU_SIGNAL", source_ref: "SIG-1", subject_type: "MEMBER", subject_ref: "100000000001",
    office_id: "RO-DEMO-01", allegation: "The account may have been used for an improper payment.",
    evidence: [{ kind: "RISK_SIGNAL", ref: "SIG-1" }], complainant: { name: "Asha Rao" },
  }));
  expect(await screen.findByText("Referred to vigilance as VIG/2026/0002.")).toBeTruthy();
});

it("shows the server's conflict detail for a referral", async () => {
  vi.mocked(command).mockRejectedValueOnce(new ApiError({ type: "/problems/already-referred", title: "Already referred",
    status: 409, detail: "This signal already has a vigilance case." }));
  renderPage(<RiskSignalsPage />, "ho.caiu", "/caiu/signals");
  fireEvent.click(await screen.findByRole("button", { name: "Refer to vigilance" }));
  const form = screen.getByRole("form", { name: "Refer signal SIG-1 to vigilance" });
  fireEvent.change(within(form).getByLabelText("Allegation"), { target: { value: "The account may have been used for an improper payment." } });
  fireEvent.submit(form);
  expect(await screen.findByText("This signal already has a vigilance case.")).toBeTruthy();
});

it.each(["ho.cvo", "zo.vigilance"])("routes %s to vigilance", (role) => {
  expect(menusFor(role)).toEqual([{ label: "Vigilance cases", to: "/vigilance" }]);
  expect(homeFor(role)).toBe("/vigilance");
});
