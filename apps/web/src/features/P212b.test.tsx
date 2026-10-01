import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { ApiError, api, command, getCurrentPolicy, getSession } from "../api/client";
import "../i18n";
import { EcrPage } from "./employer/EcrPage";
import { EstablishmentPage } from "./employer/EstablishmentPage";
import { OlrePage } from "./office/OlrePage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(), getCurrentPolicy: vi.fn(),
}));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const base = "/api/v1/employers/me";
const filingId = "ECR-1";
const filing = { filing_id: filingId, wage_month: "2026-08", type: "REGULAR", version: 1, state: "SUBMITTED",
  rule_version: "demo", trrn: "TRRN1", validation_report: null, principal_tags: [],
  members: [{ uan: "100000000001", name: "Asha" }, { uan: "100000000002", name: "Bharat" }] };
const contractor = { contractor_id: "C-1", registration_number: "REG-2", name: "Demo contractor", registered_with_epfo: true,
  establishment_id: "EST-DEMO-0002", work_order_ref: "WO-1", valid_from: "2026-01-01", valid_to: null };
let responses: Record<string, unknown>; let clients: QueryClient[];

beforeEach(() => {
  vi.clearAllMocks(); clients = [];
  responses = {
    [base]: { establishment_id: "EST-DEMO-0001", legal_name: "Demo", your_permissions: ["ecr.prepare"] },
    [`${base}/configuration`]: { coverage_type: "STATUTORY", coverage_date: null, exemption_status: "NOT_EXEMPT",
      establishment_type: "FACTORY", industry_group: "DEMO", jurisdiction_office: "RO-DEMO-01", schemes: [], sub_codes: [], address: {} },
    [`${base}/change-requests`]: [], [`${base}/kyc`]: { kyc: {}, note: "" }, [`${base}/bank-accounts`]: [],
    [`${base}/exemption`]: { exemption_status: "NOT_EXEMPT", exempted: false, note: "" },
    [`${base}/branches`]: [], [`${base}/ownership-declaration`]: { filed: false }, [`${base}/contractors`]: [contractor],
    [`${base}/signatories`]: [], [`${base}/signature-registrations`]: [], [`${base}/pending-approvals`]: { items: [] },
    "/api/v1/office/establishment-registrations": [],
    "/api/v1/office/establishment-change-requests?state=PENDING": [],
    "/api/v1/office/signature-registrations": [],
    [`${base}/ecr-filings`]: [filing], [`${base}/ecr-filings/${filingId}`]: filing,
    [`${base}/contractors/EST-DEMO-0002/compliance`]: { months: [{ wage_month: "2026-08", members: 2,
      epf_wages_paise: 2500000, contribution_paise: 600000, paid: false, filing_id: filingId, work_order_ref: "WO-1" }],
      unpaid_months: ["2026-08"], note: "Illustrative view of tagged workers and recorded challan payments only." },
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockResolvedValue({ data: { request_id: "CR-1" }, meta: {} });
  vi.mocked(getCurrentPolicy).mockResolvedValue({ data: { rule_version: "demo", effective_from: "2026-01-01", contribution: {
    epf_employee_rate_bp: 1200, eps_rate_bp: 833, eps_wage_ceiling_paise: 1500000, edli_wage_ceiling_paise: 1500000 },
    claim_types: {}, grievance_categories: [], scheduled: [] }, meta: { correlation_id: "TEST", as_of: "2026-10-01" } });
  ask.mockResolvedValue("step-up-token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });
function renderPage(page: ReactElement, role = "employer.signatory") {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client); render(<QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>);
}
function fill(form: HTMLElement, label: string, value: string) {
  fireEvent.change(within(form).getByLabelText(label), { target: { value } });
}

it("posts voluntary coverage fields and shows a compulsory coverage problem", async () => {
  vi.mocked(command).mockRejectedValueOnce(new ApiError({ type: "/problems/covered-compulsorily", title: "Establishment meets the compulsory coverage threshold", status: 409 }));
  renderPage(<EstablishmentPage />);
  const form = await screen.findByRole("form", { name: "Request voluntary coverage" });
  fill(form, "Employees", "12"); fill(form, "Employees consenting", "8");
  fill(form, "Effective from", "2026-09-01"); fill(form, "Reason", "Workers have agreed to coverage.");
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/employers/voluntary-coverage-requests", {
    employees: 12, employees_consenting: 8, effective_from: "2026-09-01", reason: "Workers have agreed to coverage.",
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "request-establishment-change", resourceId: "EST-DEMO-0001" }));
  expect(await screen.findByText("Establishment meets the compulsory coverage threshold")).toBeTruthy();
});

it("posts closure and office transfer with establishment step-up", async () => {
  renderPage(<EstablishmentPage />);
  const closure = await screen.findByRole("form", { name: "Request closure" });
  await waitFor(() => expect((within(closure).getByRole("button", { name: "Request closure" }) as HTMLButtonElement).disabled).toBe(false));
  fill(closure, "Closed on", "2026-09-20"); fill(closure, "Reason", "MERGED");
  fill(closure, "Last wage month", "2026-09"); fill(closure, "Note", "Merged into another company."); fireEvent.submit(closure);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${base}/closure-requests`, {
    closed_on: "2026-09-20", reason: "MERGED", last_wage_month: "2026-09", note: "Merged into another company.",
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "request-closure", resourceId: "EST-DEMO-0001" }));
  const transfer = screen.getByRole("form", { name: "Request office transfer" });
  fill(transfer, "To office", "RO-DEMO-02"); fill(transfer, "Effective from", "2026-10-01");
  fill(transfer, "Reason", "Jurisdiction moved to the second office."); fireEvent.submit(transfer);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${base}/office-transfer-requests`, {
    to_office_id: "RO-DEMO-02", effective_from: "2026-10-01", reason: "Jurisdiction moved to the second office.",
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "request-office-transfer", resourceId: "EST-DEMO-0001" }));
});

it("renders a closure request with its date and reason in the office queue", async () => {
  responses["/api/v1/office/establishment-change-requests?state=PENDING"] = [{ request_id: "CR-9", establishment_id: "EST-DEMO-0001",
    legal_name: "Demo", kind: "CLOSURE", reason: "Merged into another company.", state: "PENDING",
    changes: { closed_on: { from: null, to: "2026-09-20" }, closure_reason: { from: null, to: "MERGED" } } }];
  renderPage(<OlrePage />, "fo.oic");
  expect(await screen.findByText(/2026-09-20/)).toBeTruthy();
  expect(screen.getByText(/closure reason:.*Merged/i)).toBeTruthy();
});

it("tags only selected UANs from the filing's member rows", async () => {
  renderPage(<EcrPage />, "employer.operator");
  const form = await screen.findByRole("form", { name: "Tag workers to a principal employer" });
  fill(form, "Work order reference", "WO-5");
  fireEvent.click(within(form).getByLabelText(/100000000002/)); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${base}/ecr-filings/${filingId}/principal-employer-tags`, {
    principal_establishment_id: "EST-DEMO-0002", work_order_ref: "WO-5", uans: ["100000000002"],
  }));
});

it("explains the tagging permission needed by a signatory", async () => {
  responses[base] = { establishment_id: "EST-DEMO-0001", legal_name: "Demo", your_permissions: ["ecr.submit"] };
  renderPage(<EcrPage />, "employer.signatory");
  const form = await screen.findByRole("form", { name: "Tag workers to a principal employer" });
  expect(screen.getByText("This account needs the ecr.prepare permission to submit tags.")).toBeTruthy();
  expect((within(form).getByRole("button", { name: "Tag selected workers" }) as HTMLButtonElement).disabled).toBe(true);
});

it("shows an unpaid contractor month in the compliance table", async () => {
  renderPage(<EstablishmentPage />, "employer.owner");
  fireEvent.click(await screen.findByRole("button", { name: "Compliance" }));
  const table = await screen.findByRole("table", { name: "Compliance months" });
  const row = within(table).getByRole("row", { name: /2026-08/ });
  expect(row.classList.contains("compliance-unpaid")).toBe(true); expect(within(row).getByText("Unpaid")).toBeTruthy();
});
