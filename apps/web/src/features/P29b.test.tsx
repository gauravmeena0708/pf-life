import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { TrustPage } from "./exempted/TrustPage";
import { PassbookPage } from "./member/PassbookPage";
import { PensionEstimate } from "./member/PensionEstimate";
import { ServicePage } from "./member/ServicePage";
import { TrustReconciliation } from "./office/TrustReconciliation";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(), newIdempotencyKey: () => "key-1" }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

let responses: Record<string, unknown>;
beforeEach(() => {
  vi.clearAllMocks(); ask.mockResolvedValue("step-token");
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.da_accounts" });
  responses = {};
  vi.mocked(api).mockImplementation(async (path) => {
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockResolvedValue({ data: {}, meta: {} });
});
afterEach(cleanup);
function show(page: ReactElement) { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const trust = { source: "Demo Steel PF Trust", fetched_at: "2026-09-30T10:00:00Z", stale: false, balance: { employee_paise: 120000, employer_paise: 80000 },
  entries: [{ date: "2026-06-30", kind: "CONTRIBUTION", amount_paise: 5000, note: "June contribution" }], service_from: "2020-01-01", service_to: "2026-06-30" };

it.each([
  ["fresh", trust, "As reported by the trust, fetched at"],
  ["stale", { ...trust, stale: true }, "Last fetched"],
  ["unavailable", { unavailable: true, contact: trust.source }, `Contact ${trust.source} for this balance`],
])("shows the %s trust passbook section", async (_state, section, message) => {
  responses["/api/v1/members/me/passbook"] = { accounts: [{ account_link_id: "AL-0915", entries: [], trust: section }], pending: [] };
  responses["/api/v1/members/me/annual-statements/2026-27"] = { accounts: [], note: "" };
  responses["/api/v1/members/me/tax/taxable-interest?financialYear=2026-27"] = { taxable_interest_paise: 0, non_taxable_interest_paise: 0, employee_contributions_paise: 0, threshold_paise: 0, working: "", interest_credited: false, note: "" };
  show(<PassbookPage />);
  expect(await screen.findByRole("region", { name: `PF held by ${trust.source}` })).toBeTruthy();
  expect(screen.getByText(new RegExp(message))).toBeTruthy();
  expect(screen.getByText("Pension (EPS) service for this member ID is with EPFO.")).toBeTruthy();
  if (_state !== "unavailable") { expect(screen.getByText("₹2,000.00")).toBeTruthy(); expect(screen.getByText("June contribution")).toBeTruthy(); }
});

const leg = { transfer_id: "TR-1", direction: "TRUST_TO_EPFO", pf_leg: { state: "AWAITING_TRUST", label: "Waiting for the PF from Demo Steel PF Trust", detail: {} },
  eps_leg: { state: "WAITING_FOR_PF", label: "Waiting for the PF transfer to complete", detail: {} } };
it("shows two transfer legs and the automatic pension explanation", async () => {
  responses["/api/v1/members/me/service-history"] = { uan: "100000000912", member_ids: [], total_service_months: 0 };
  responses["/api/v1/members/me/applications"] = [];
  responses["/api/v1/members/me/transfers/auto"] = { primary_account_link_id: null, reasons: [], note: "", eligible: [], history: [] };
  responses["/api/v1/members/me/transfer-legs"] = { transfers: [leg] };
  show(<ServicePage />);
  const panel = await screen.findByLabelText("Transfer TR-1");
  expect(within(panel).getByText("Awaiting trust")).toBeTruthy();
  expect(within(panel).getByText("Waiting for PF")).toBeTruthy();
  expect(screen.getByText(/pension leg starts by itself/)).toBeTruthy();
});

it("submits trust amounts in paise with an idempotency key", async () => {
  responses["/api/v1/exempted/me/profile"] = { establishment: { establishment_id: "EST-DEMO-0004", legal_name: "Demo Steel Works" }, kind: "S17_1A", kind_description: "Whole establishment", pf_exempt: true, pension_exempt: false, edli_exempt: false, notification_no: "N-1", notification_date: "2020-01-01", effective_from: "2020-01-01", status: "ACTIVE", trust_name: trust.source, conditions: [{ number: 3, description: "Enrol employees." }], note: "PF with trust." };
  responses["/api/v1/exempted/me/annexure-k-requests"] = { requests: [{ annexure_id: "AKT-1", transfer_id: "TR-1", from_account_link_id: "AL-0918", to_account_link_id: "AL-0919", state: "REQUESTED", employee_paise: null, employer_paise: null }] };
  show(<TrustPage />);
  const form = await screen.findByRole("form", { name: "Submit Annexure K AKT-1" });
  for (const [label, value] of [["Employee PF (₹)", "1200.50"], ["Employer PF (₹)", "800"], ["Service from", "2020-01-01"], ["Service to", "2026-06-30"], ["Breaks (months)", "2"], ["Interest note", "Interest included"]]) fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/exempted/me/annexure-k-submissions", {
    annexure_id: "AKT-1", employee_paise: 120050, employer_paise: 80000, service_from: "2020-01-01", service_to: "2026-06-30", breaks_months: 2, interest_note: "Interest included",
  }, { idempotencyKey: "key-1" }));
});

it("lists the trusts' Annexure K and reconciles one against its submitted total", async () => {
  responses["/api/v1/office/exempted/annexure-k?state=SUBMITTED"] = { annexure_k: [{ annexure_id: "AKT-1", transfer_id: "TR-1", uan: "100000000912",
    from_account_link_id: "AL-0918", to_account_link_id: "AL-0919", state: "SUBMITTED", submitted_total_paise: 200000, service_from: "2020-01-01",
    service_to: "2026-06-30", breaks_months: 2 }] };
  responses["/api/v1/office/exempted/annexure-k?state=MISMATCH"] = { annexure_k: [] };
  vi.mocked(command).mockResolvedValue({ data: { annexure_id: "AKT-1", state: "MISMATCH", difference_paise: -100, received_paise: 199900 }, meta: {} });
  show(<TrustReconciliation />); const form = await screen.findByRole("form", { name: "Reconcile AKT-1" });
  for (const [label, value] of [["Receipt reference", "R-1"], ["Amount received (₹)", "1999"]]) fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "reconcile-trust-annexure-k", resourceId: "AKT-1", amountPaise: 200000 })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/exempted/annexure-k/AKT-1/reconciliations", { receipt_ref: "R-1", received_paise: 199900 }, { stepUpToken: "step-token" }));
  expect(await screen.findByText(/Difference.*1/)).toBeTruthy();
});

it("routes trust users to their workspace", () => { expect(menusFor("exempted.trust")).toEqual([{ label: "Trust", to: "/exempted" }]); expect(homeFor("exempted.trust")).toBe("/exempted"); });
it("shows who holds PF for each pension service spell", async () => {
  responses["/api/v1/members/me/pension-eligibility-preview"] = { rule_version: "demo", service_months_so_far: 12, pensionable_salary_paise: 1500000, min_service_years: 10, scenarios: [], note: "Illustrative", service_by_member_id: [
    { account_link_id: "AL-0918", from: "2020-01-01", to: "2026-06-30", months: 78, breaks_months: 0, pf_with: `TRUST ${trust.source}` },
    { account_link_id: "AL-0919", from: "2026-07-01", to: null, months: 3, breaks_months: 0, pf_with: "EPFO" }] };
  show(<PensionEstimate />); const table = await screen.findByRole("table", { name: /service by member/i });
  expect(within(table).getByText("PF with")).toBeTruthy(); expect(within(table).getByText(trust.source)).toBeTruthy(); expect(within(table).getByText("EPFO")).toBeTruthy();
});
