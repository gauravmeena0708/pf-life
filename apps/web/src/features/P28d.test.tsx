import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ApiError, api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { PublicLookups } from "../pages/PublicLookups";
import { InterestPage } from "./finance/InterestPage";
import { GrievanceDetailPage } from "./grievance/GrievanceDetailPage";
import { GrievanceOfficePage } from "./grievance/GrievanceOfficePage";
import { CircularsPage } from "./ho/CircularsPage";
import { ExemptedPage } from "./office/ExemptedPage";
import { PublicCircularsPage } from "./public/CircularsList";
import { EReportCardPage } from "./public/EReportCardPage";
import { PublicClaimStatusPage, PublicGrievancesPage } from "./public/PublicGrievancesPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(),
}));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const uan = "100000000001";
const header = "uan,account_link_id,employee_rupees,employer_rupees,pension_rupees";
const content = `${header}\n${uan},AL-1,1000,500,100\n100000000002,AL-2,2000,1000,200`;
const rateBody = { rate_bp: 825, cbt_recommended_on: "2026-03-01", ministry_concurrence_ref: "MOL-DEMO-01", ministry_concurrence_on: "2026-03-20", note: "Approved for demonstration." };
const rateResult = { declaration_id: "IRD-1", financial_year: "2025-26", rate_bp: 825, next_step: "A draft rule set is prepared for approval.",
  recorded: [{ declaration_id: "IRD-1", rate_bp: 825, ministry_concurrence_ref: "MOL-DEMO-01", created_at: "2026-03-20" }] };
const ingestionResult = { batch_id: "PA-1", establishment_id: "EST-DEMO-0003", legal_name: "Demo trust", transfer_reference: "TRUST-1", members: 2, total_paise: 480000,
  lines: [{ line: 2, uan, account_link_id: "AL-1", employee_paise: 100000, employer_paise: 50000, pension_paise: 10000, journal_id: "JRN-1" }] };
const grievance = { grievance_id: "GRV-1234ABCD", category: "CLAIM_DELAY", subject: "Delayed claim", description: "Please review the delayed claim.",
  state: "IN_PROGRESS", office_id: "RO-1", tier: "RO", version: 2, sla_due_at: "2026-10-01", resolved_at: null, resolution: null,
  entries: [], documents: [], linked_claim_id: null };
const circular = { circular_id: "CIR-1", number: "DEMO/01", version: 1, title: "Demonstration circular", category: "GENERAL", issued_on: "2026-03-20",
  summary: "Demonstration summary.", state: "CURRENT", sha256: "abc123", published_at: "2026-03-20", body: "Full circular body for the demonstration." };
const circularList = { circulars: [circular], categories: ["GENERAL", "CLAIMS"], note: "Synthetic circulars." };
let responses: Record<string, unknown>;
let clients: QueryClient[];
let challengeNumber: number;

beforeEach(() => {
  vi.clearAllMocks(); clients = []; challengeNumber = 0;
  responses = {
    "/api/v1/grievances/GRV-1234ABCD": grievance,
    "/api/v1/public/offices": [{ office_id: "RO-1", name: "Current office", zone_id: "ZO-1" }, { office_id: "RO-2", name: "Receiving office", zone_id: "ZO-2" }],
    "/api/v1/public/circulars": circularList,
    "/api/v1/public/circulars?category=CLAIMS&q=demonstration": circularList,
    "/api/v1/public/circulars?number=DEMO%2F01": { ...circularList, circulars: [circular, { ...circular, circular_id: "CIR-0", version: 0, state: "SUPERSEDED" }] },
    "/api/v1/public/defaulting-establishments": { establishments: [], label: "SYNTHETIC", note: "Demo only." },
    "/api/v1/public/establishments?query=Demo&mode=name&match=contains&page=1": [{ establishment_id: "EST-DEMO-0003", registration_number: "DEMO/03", legal_name: "Demo trust", office_id: "RO-1", status: "VERIFIED" }],
    "/api/v1/public/establishments/EST-DEMO-0003/e-report-card": { establishment_id: "EST-DEMO-0003", as_of: "2026-09-30", months: [{ wage_month: "2026-08", due_date: "2026-09-15", status: "PAID_LATE", paid_on: "2026-09-17", days_late: 2 }], counts: { PAID_LATE: 1 }, remitted_paise: 123456, note: "Synthetic filing history." },
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/public/demo-challenges") return { data: { challenge_id: `QUESTION-${++challengeNumber}`, prompt: "What is 2 + 3?" }, meta: {} };
    if (path.startsWith("/api/v1/office/accounts/interest-postings?")) return { data: { financial_year: "2025-26", rate_bp: null, year_ended: true, accounts: [], history: [], rule_version: "demo", method: "Illustrative", total_to_credit_paise: 0 }, meta: {} };
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockImplementation(async (_method, path) => ({ data: path === "/api/v1/ai/grievances/classify" ? { suggested_category: "CLAIM_DELAY", matched_terms: [], confidence: "low", note: "Advisory only.", interaction_id: "AI-1" }
    : path.includes("interest-rates") ? rateResult
    : path.includes("past-accumulation") ? ingestionResult : path === "/api/v1/ho/circulars" ? circular
    : { registration_no: "GRV-1234ABCD", claim_id: "CLM-1234ABCD", state: "ROUTED", office_id: "RO-1", sla_due_at: "2026-10-01", note: "Keep this reference.", steps: [] }, meta: {} }));
  vi.mocked(getSession).mockResolvedValue({ authenticated: false });
  ask.mockResolvedValue("step-up-token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });

function renderPage(page: ReactElement, role?: string, entry = "/", route?: string) {
  vi.mocked(getSession).mockResolvedValue({ authenticated: !!role, stakeholder: role });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}>
    {route ? <Routes><Route path={route} element={page} /></Routes> : page}
  </MemoryRouter></QueryClientProvider>);
}
function fill(form: HTMLElement, label: string, value: string) {
  fireEvent.change(within(form).getByLabelText(label), { target: { value } });
}
async function rateForm() {
  renderPage(<InterestPage />, "ho.fa_cao");
  const form = await screen.findByRole("form", { name: "Record the interest rate" });
  fill(form, "Financial year to record", "2025-26"); fill(form, "Rate (%)", "8.25");
  fill(form, "CBT recommended on", rateBody.cbt_recommended_on);
  fill(form, "Ministry concurrence reference", rateBody.ministry_concurrence_ref);
  fill(form, "Ministry concurred on", rateBody.ministry_concurrence_on); fill(form, "Note (optional)", rateBody.note);
  return form;
}
async function ingestionForm() {
  renderPage(<ExemptedPage />, "fo.exemption");
  const form = await screen.findByRole("form", { name: "Past accumulation ingestion" });
  fill(form, "Transfer reference", "TRUST-1"); fill(form, header, content);
  return form;
}
async function publicForm(kind: string) {
  renderPage(kind === "claim" ? <PublicClaimStatusPage /> : <PublicGrievancesPage />);
  const form = screen.getByRole("form", { name: kind === "file" ? "File a grievance" : kind === "status" ? "Check grievance status" : "Check claim status" });
  if (kind === "file") {
    fill(form, "Name", "Demo Member"); fill(form, "Complainant type", "MEMBER"); fill(form, "Category", "CLAIM_DELAY");
    fill(form, "Subject", "Delayed claim"); fill(form, "Description", "Please review the delayed claim."); fill(form, "Reference (optional)", "CLM-1234ABCD");
  }
  if (kind === "status") fill(form, "Registration number", "GRV-1234ABCD");
  if (kind === "claim") { fill(form, "Claim ID", "CLM-1234ABCD"); fill(form, "UAN", uan); }
  else fill(form, "Mobile number", "9876543210");
  fill(form, "Mock one-time code", "123456");
  fireEvent.click(within(form).getByRole("button", { name: "Get one-use demo question" }));
  await within(form).findByLabelText("What is 2 + 3?"); fill(form, "What is 2 + 3?", "5");
  return form;
}

it("records percent as basis points and binds step-up to the financial year and rate", async () => {
  fireEvent.submit(await rateForm());
  await waitFor(() => expect(command).toHaveBeenCalledWith("PUT", "/api/v1/ho/config/interest-rates/2025-26", rateBody, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "record-interest-rate", resourceId: "2025-26", amountPaise: 825, summary: expect.any(String) });
  expect(await screen.findByText(rateResult.next_step)).toBeTruthy(); expect(screen.getByText("8.25%")).toBeTruthy();
});
it("binds the full CSV total in paise to ingestion and shows journal IDs", async () => {
  const form = await ingestionForm(); expect(within(form).getByText("₹4,800.00")).toBeTruthy(); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/exempted/EST-DEMO-0003/past-accumulation-ingestions",
    { transfer_reference: "TRUST-1", content }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "ingest-past-accumulation", resourceId: "EST-DEMO-0003", amountPaise: 480000, summary: expect.any(String) });
  expect(await screen.findByText("JRN-1")).toBeTruthy();
});
it("computes decimal rupee columns in paise without floating-point drift", async () => {
  const form = await ingestionForm(); fill(form, header, `${uan},AL-1,1.01,2.02,3.03`); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ amountPaise: 606 })));
});
it.each(["rate", "ingestion"])("does not send %s when step-up is cancelled", async (kind) => {
  ask.mockResolvedValue(null); fireEvent.submit(kind === "rate" ? await rateForm() : await ingestionForm());
  await waitFor(() => expect(ask).toHaveBeenCalled()); expect(command).not.toHaveBeenCalled();
});
it.each(["rate", "ingestion"])("freezes %s inputs while awaiting step-up confirmation", async (kind) => {
  let confirm!: (token: string | null) => void;
  ask.mockImplementation(() => new Promise((resolve) => { confirm = resolve; }));
  const form = kind === "rate" ? await rateForm() : await ingestionForm(); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalled());
  expect((within(form).getByRole("group") as HTMLFieldSetElement).disabled).toBe(true);
  expect(command).not.toHaveBeenCalled(); confirm(null);
  await waitFor(() => expect((within(form).getByRole("group") as HTMLFieldSetElement).disabled).toBe(false));
});
it("rejects a nonconsecutive financial year before step-up", async () => {
  const form = await rateForm(); fill(form, "Financial year to record", "2025-27"); fireEvent.submit(form);
  expect(await screen.findByRole("alert")).toBeTruthy(); expect(ask).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
});
it("rejects malformed CSV before requesting a money-bound confirmation", async () => {
  const form = await ingestionForm(); fill(form, header, `${uan},AL-1,bad,500,100`); fireEvent.submit(form);
  expect(await screen.findByText("Check the member lines")).toBeTruthy(); expect(ask).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
});
it.each(["rate", "ingestion"])("shows the service's 422 errors for %s", async (kind) => {
  vi.mocked(command).mockRejectedValue(new ApiError({ type: "/problems/validation", title: "Review this record", status: 422,
    detail: "The record could not be accepted.", errors: ["Line 2: account does not belong to the establishment.", { field: "note", message: "Please check." }] }));
  fireEvent.submit(kind === "rate" ? await rateForm() : await ingestionForm());
  expect(await screen.findByText("The record could not be accepted.")).toBeTruthy();
  expect(screen.getByText("Line 2: account does not belong to the establishment.")).toBeTruthy(); expect(screen.getByText("note: Please check.")).toBeTruthy();
});
it.each(["file", "status", "claim"])("sends %s without login with its own challenge ID and integer answer", async (kind) => {
  fireEvent.submit(await publicForm(kind));
  const path = kind === "file" ? "grievances" : kind === "status" ? "grievances/status-lookups" : "claims/status-lookups";
  const fields = kind === "file" ? { name: "Demo Member", mobile: "9876543210", complainant_type: "MEMBER", category: "CLAIM_DELAY", subject: "Delayed claim", description: "Please review the delayed claim.", reference: "CLM-1234ABCD" }
    : kind === "status" ? { registration_no: "GRV-1234ABCD", mobile: "9876543210" } : { claim_id: "CLM-1234ABCD", uan };
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `/api/v1/public/${path}`, { ...fields, otp: "123456", challenge_id: "QUESTION-1", answer: 5 }));
  expect(ask).not.toHaveBeenCalled(); expect(screen.getByText("Keep this reference.")).toBeTruthy();
});
it("keeps filing and status challenges separate and retires a consumed challenge", async () => {
  const filing = await publicForm("file");
  const status = screen.getByRole("form", { name: "Check grievance status" });
  fireEvent.click(within(status).getByRole("button", { name: "Get one-use demo question" }));
  await within(status).findByLabelText("What is 2 + 3?");
  fireEvent.submit(filing); await waitFor(() => expect(command).toHaveBeenCalled());
  expect(within(filing).queryByLabelText("What is 2 + 3?")).toBeNull();
  expect(within(status).getByLabelText("What is 2 + 3?")).toBeTruthy();
  fireEvent.submit(filing); expect(command).toHaveBeenCalledTimes(1);
  fireEvent.click(within(filing).getByRole("button", { name: "Get one-use demo question" }));
  await within(filing).findByLabelText("What is 2 + 3?"); fill(filing, "What is 2 + 3?", "5"); fireEvent.submit(filing);
  await waitFor(() => expect(command).toHaveBeenLastCalledWith("POST", "/api/v1/public/grievances", expect.objectContaining({ challenge_id: "QUESTION-3", answer: 5 })));
});
it.each(["otp", "answer"])("rejects invalid public %s without consuming the challenge", async (kind) => {
  const form = await publicForm("claim"); fill(form, kind === "otp" ? "Mock one-time code" : "What is 2 + 3?", kind === "otp" ? "000000" : "5.5");
  fireEvent.submit(form); expect(await screen.findByRole("alert")).toBeTruthy(); expect(command).not.toHaveBeenCalled();
  expect(within(form).getByLabelText("What is 2 + 3?")).toBeTruthy();
});
it("retires a public challenge after a service error and shows the problem", async () => {
  vi.mocked(command).mockRejectedValue(new ApiError({ type: "/problems/challenge", title: "Incorrect answer", status: 422, detail: "Get a new question." }));
  const form = await publicForm("status"); fireEvent.submit(form);
  expect(await screen.findByText("Get a new question.")).toBeTruthy(); expect(within(form).queryByLabelText("What is 2 + 3?")).toBeNull();
});
it("shows the 429 problem for a reminder already sent today", async () => {
  renderPage(<GrievanceDetailPage />, "member", "/member/grievances/GRV-1234ABCD", "/member/grievances/:grievanceId");
  const form = await screen.findByRole("form", { name: "Send a reminder" }); fill(form, "Reminder note (optional)", "Please follow up.");
  vi.mocked(command).mockRejectedValue(new ApiError({ type: "/problems/reminder-too-soon", title: "Already reminded today", status: 429, detail: "You can send another tomorrow." }));
  fireEvent.submit(form); expect(await screen.findByText("You can send another tomorrow.")).toBeTruthy();
  expect(command).toHaveBeenCalledWith("POST", "/api/v1/grievances/GRV-1234ABCD/reminders", { note: "Please follow up." });
});
it.each(["true", "false"])("sends resolved-grievance feedback with boolean satisfaction %s", async (satisfied) => {
  responses["/api/v1/grievances/GRV-1234ABCD"] = { ...grievance, state: "RESOLVED" };
  renderPage(<GrievanceDetailPage />, "member", "/member/grievances/GRV-1234ABCD", "/member/grievances/:grievanceId");
  const form = await screen.findByRole("form", { name: "Grievance feedback" });
  expect(screen.queryByRole("form", { name: "Send a reminder" })).toBeNull();
  fill(form, "Rating", "4"); fill(form, "Are you satisfied?", satisfied); fill(form, "Comment (optional)", "Thank you."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/grievances/GRV-1234ABCD/feedback", { rating: 4, satisfied: satisfied === "true", comment: "Thank you." }));
});
it("excludes the current office and transfers to the chosen office with a reason", async () => {
  renderPage(<GrievanceOfficePage />, "fo.pro", "/office/grievances/GRV-1234ABCD", "/office/grievances/:grievanceId");
  const form = await screen.findByRole("form", { name: "Transfer to another office" }); await within(form).findByRole("option", { name: /Receiving office/ });
  expect(within(form).queryByRole("option", { name: /Current office/ })).toBeNull();
  fill(form, "Receiving office", "RO-2"); fill(form, "Transfer reason", "The establishment belongs to this office."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/grievances/GRV-1234ABCD/office-transfers",
    { to_office_id: "RO-2", reason: "The establishment belongs to this office." }, { stepUpToken: undefined }));
  expect(await screen.findByText("This grievance has been transferred; the receiving office now handles it.")).toBeTruthy();
});
it("reads circular bodies, searches by category and title, and opens versions by number", async () => {
  renderPage(<PublicCircularsPage />); fireEvent.click(await screen.findByRole("button", { name: circular.title }));
  expect(screen.getByText(circular.body)).toBeTruthy();
  const form = screen.getByRole("form", { name: "Filter circulars" }); fill(form, "Category", "CLAIMS"); fill(form, "Search circulars", "demonstration"); fireEvent.submit(form);
  await waitFor(() => expect(api).toHaveBeenCalledWith("/api/v1/public/circulars?category=CLAIMS&q=demonstration"));
  fireEvent.click((await screen.findAllByRole("link", { name: "Versions of DEMO/01" }))[0]);
  expect(await screen.findByText(/Version 0/)).toBeTruthy(); expect(api).toHaveBeenCalledWith("/api/v1/public/circulars?number=DEMO%2F01");
});
it("publishes a circular and refreshes the current list", async () => {
  renderPage(<CircularsPage />, "ho.publicity"); const form = await screen.findByRole("form", { name: "Publish a circular" });
  for (const [label, value] of [["Number", circular.number], ["Title", circular.title], ["Category", circular.category], ["Issued on", circular.issued_on], ["Summary", circular.summary], ["Body", circular.body]]) fill(form, label, value);
  await screen.findByRole("button", { name: circular.title }); const before = vi.mocked(api).mock.calls.filter(([path]) => path === "/api/v1/public/circulars").length;
  fireEvent.submit(form); expect(await screen.findByText("Published circular DEMO/01, version 1.")).toBeTruthy();
  expect(command).toHaveBeenCalledWith("POST", "/api/v1/ho/circulars", { number: circular.number, title: circular.title, category: circular.category, issued_on: circular.issued_on, summary: circular.summary, body: circular.body });
  await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([path]) => path === "/api/v1/public/circulars").length).toBeGreaterThan(before));
});
it("opens the e-Report Card from an establishment search result and displays rupees", async () => {
  renderPage(<Routes><Route path="/public" element={<PublicLookups />} /><Route path="/public/establishments/:estId/e-report-card" element={<EReportCardPage />} /></Routes>, undefined, "/public");
  fireEvent.change(screen.getByLabelText("Search term"), { target: { value: "Demo" } }); fireEvent.click(screen.getByRole("button", { name: "Search register" }));
  fireEvent.click(await screen.findByRole("button", { name: "e-Report Card" }));
  expect(await screen.findByText("₹1,234.56")).toBeTruthy(); expect(screen.getAllByText("Paid late").length).toBeGreaterThan(0);
});
it.each([["ho.publicity", "/ho/circulars"], ["fo.exemption", "/office/exempted"], ["ho.fa_cao", "/finance/interest"]])("links %s to its landing page", (role, path) => {
  expect(homeFor(role)).toBe(path);
  expect(menusFor(role).some((group) => group.to?.startsWith(path) || group.items?.some((item) => item.to?.startsWith(path)))).toBe(true);
});
it("provides the public menu without a login", () => {
  expect(menusFor(undefined)[0].items?.map((item) => item.label)).toEqual(["Grievance (without login)", "Grievance status", "Claim status", "Inoperative account search", "Circulars"]);
});
it.each(["finance", "exemption", "publicity"])("hides the %s command form from unrelated roles", async (kind) => {
  renderPage(kind === "finance" ? <InterestPage /> : kind === "exemption" ? <ExemptedPage /> : <CircularsPage />, "member");
  await screen.findByText(kind === "finance" ? "Interest rates are recorded by HO Finance and Accounts." : kind === "exemption" ? "This service is available to the Exemption cell." : "Publishing is available to HO Public Relations.");
  expect(screen.queryByRole("form", { name: kind === "finance" ? "Record the interest rate" : kind === "exemption" ? "Past accumulation ingestion" : "Publish a circular" })).toBeNull();
});
it.each([["record-interest-rate", 825, "8.25%"], ["ingest-past-accumulation", 480000, "₹4,800.00"]])("displays the correct unit for %s confirmation and keeps its numeric binding", async (action, amountPaise, displayed) => {
  const { StepUpDialog: ActualDialog } = await vi.importActual<typeof import("./stepup/StepUpDialog")>("./stepup/StepUpDialog");
  const original = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value(this: HTMLDialogElement) { this.open = true; } });
  vi.mocked(command).mockResolvedValue({ data: { challenge_id: "STEP-1", demo_otp: "123456", demo_notice: "Mock code." }, meta: {} });
  try {
    renderPage(<ActualDialog request={{ action, amountPaise, resourceId: "DEMO-REFERENCE", summary: "Confirm the demonstration record." }} onConfirmed={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText(displayed)).toBeTruthy();
    await screen.findByText("Mock code.");
    expect(command).toHaveBeenCalledWith("POST", "/api/v1/security/step-up-challenges", {
      action, amount_paise: amountPaise, resource_id: "DEMO-REFERENCE", resource_version: null, summary: "Confirm the demonstration record.",
    });
  } finally {
    cleanup();
    if (original) Object.defineProperty(HTMLDialogElement.prototype, "showModal", original);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  }
});
