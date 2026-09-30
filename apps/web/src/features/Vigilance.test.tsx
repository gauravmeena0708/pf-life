import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { ApiError, api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
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
  const table = screen.getByRole("table");
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
