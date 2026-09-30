import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ApiError, api, command, getMyPermissions, getSession } from "../api/client";
import "../i18n";
import { JointDeclarations } from "./employer/JointDeclarations";
import { MemberActionsPage } from "./employer/MemberActionsPage";
import { ClaimDetailPage } from "./member/ClaimDetailPage";
import { NominationPage } from "./member/NominationPage";
import { ServicePage } from "./member/ServicePage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(),
  api: vi.fn(), command: vi.fn(), getSession: vi.fn(), getMyPermissions: vi.fn(),
}));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const memberBase = "/api/v1/members/me";
const employerBase = "/api/v1/employers/me";
const uan = "100000000001";
const nomination = { nomination_id: "NOM-1", state: "CURRENT", has_family: true,
  signed_with: "MOCK_AADHAAR_ESIGN", signed_at: "2026-09-30",
  nominees: [{ name: "Existing nominee", relation: "SPOUSE", date_of_birth: "1990-01-01", share_bp: 10000, minor: false, guardian_name: null }] };
const nominations = { uan, current: nomination, history: [], aadhaar_verified: true,
  relations: ["SPOUSE", "CHILD", "OTHER"], family_relations: ["SPOUSE", "CHILD"], note: "Mock nomination service." };
const claim = { claim_id: "CLM-1", account_link_id: "AL-1", claim_type: "FINAL_SETTLEMENT", form_type: "19",
  amount_paise: 123450, state: "PENDING_EMPLOYER_ATTESTATION", version: 7, rule_version: "mock", summary: "Final settlement",
  decision_reason: null, payment_id: null, next_step: "Your employer must attest this claim.", tax: null, timeline: [] };
const banks = { claim_id: claim.claim_id, switchable: true, current_account_last4: "1111",
  verified_accounts: [{ bank_ifsc: "SBIN0000001", bank_account_last4: "2222" }] };
const attestation = { claim_id: claim.claim_id, uan, account_link_id: "AL-1", claim_type: claim.claim_type,
  form_type: "19", amount_paise: claim.amount_paise, version: 7, summary: "Final settlement", filed_at: "2026-09-30", why: "Employer records required." };
let responses: Record<string, unknown>;
let clients: QueryClient[];

beforeEach(() => {
  vi.clearAllMocks();
  clients = [];
  responses = {
    [`${memberBase}/nominations`]: nominations,
    [`${memberBase}/service-history`]: { uan, member_ids: [], total_service_months: 0 },
    [`${memberBase}/applications`]: [],
    [`${memberBase}/transfers/auto`]: { primary_account_link_id: "AL-2", reasons: [], eligible: [
      { transfer_id: "AT-1", state: "AWAITING_CONFIRMATION", uan, from_account_link_id: "AL-1", to_account_link_id: "AL-2",
        date_of_exit: "2026-08-31", amount_paise: 123450 }], history: [], note: "Mock auto-transfer." },
    [`${memberBase}/claims/CLM-1`]: claim,
    [`${memberBase}/claims/CLM-1/bank-details`]: banks,
    [employerBase]: { establishment_id: "EST-1" },
    [`${employerBase}/approvals`]: [], [`${employerBase}/transfer-requests`]: [],
    [`${employerBase}/pending-approvals`]: { items: [], note: "Mock pending approvals." },
    [`${employerBase}/claim-attestations`]: [attestation], [`${employerBase}/joint-declarations`]: [],
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockResolvedValue({ data: { case_id: "CASE-1" }, meta: {} });
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "member" });
  vi.mocked(getMyPermissions).mockResolvedValue({ data: { stakeholder: "employer.operator", endpoints: [] } });
  ask.mockResolvedValue("step-up-token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });

function renderPage(page: ReactElement, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/" element={page} /><Route path="/member/claims/:claimId" element={page} /></Routes>
  </MemoryRouter></QueryClientProvider>);
}
function fill(form: HTMLElement, label: string, value: string) {
  fireEvent.change(within(form).getByLabelText(label), { target: { value } });
}
async function nominationForm() {
  renderPage(<NominationPage />);
  const form = await screen.findByRole("form", { name: "New e-Nomination" });
  fill(form, "Name", "First nominee"); fill(form, "Relation", "SPOUSE"); fill(form, "Date of birth", "1990-01-01");
  return form;
}

it("converts nominee percentages to basis points and signs using the member UAN", async () => {
  const form = await nominationForm();
  fill(form, "Share (%)", "60.25");
  fireEvent.click(within(form).getByRole("button", { name: "Add nominee" }));
  const row = within(form).getByRole("group", { name: "Nominee 2" });
  fill(row, "Name", "Second nominee"); fill(row, "Relation", "CHILD"); fill(row, "Date of birth", "2015-03-10");
  fill(row, "Share (%)", "39.75"); fill(row, "Guardian name (required for a minor)", "Guardian");
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${memberBase}/nominations`, {
    has_family: true, nominees: [
      { name: "First nominee", relation: "SPOUSE", date_of_birth: "1990-01-01", share_bp: 6025 },
      { name: "Second nominee", relation: "CHILD", date_of_birth: "2015-03-10", share_bp: 3975, guardian_name: "Guardian" },
    ],
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "e-nominate", resourceId: uan }));
  expect(screen.getByText("Existing nominee")).toBeTruthy();
});

it("removes nominee rows and allows non-family relations when the family checkbox is cleared", async () => {
  const form = await nominationForm();
  fireEvent.click(within(form).getByRole("button", { name: "Add nominee" }));
  fireEvent.click(within(form).getByRole("button", { name: "Remove nominee 2" }));
  expect(within(form).queryByRole("group", { name: "Nominee 2" })).toBeNull();
  fireEvent.click(within(form).getByLabelText("I have a family"));
  fill(form, "Relation", "OTHER");
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${memberBase}/nominations`, expect.objectContaining({ has_family: false }), expect.anything()));
});

it("rejects a share total below 100% before asking for step-up", async () => {
  const form = await nominationForm(); fill(form, "Share (%)", "90"); fireEvent.submit(form);
  expect(await screen.findByText("Error: Enter nominee details and shares totalling 100%.")).toBeTruthy();
  expect(ask).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
});

it("does not post a nomination when step-up is cancelled", async () => {
  ask.mockResolvedValue(null);
  const form = await nominationForm(); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalled());
  await waitFor(() => expect((within(form).getByRole("button", { name: "Sign with Aadhaar e-sign (mock)" }) as HTMLButtonElement).disabled).toBe(false));
  expect(command).not.toHaveBeenCalled();
});

it("shows the detail and all validation errors returned by a 422 problem", async () => {
  vi.mocked(command).mockRejectedValue(new ApiError({ type: "/problems/nomination-invalid", title: "This nomination cannot be signed",
    status: 422, detail: "Please check the nominees.", errors: ["A guardian is required for a minor.", { field: "nominees.0.relation", message: "Relation is not permitted." }] }));
  const form = await nominationForm(); fireEvent.submit(form);
  expect(await screen.findByText("Please check the nominees.")).toBeTruthy();
  expect(screen.getByText("A guardian is required for a minor.")).toBeTruthy();
  expect(screen.getByText("nominees.0.relation: Relation is not permitted.")).toBeTruthy();
});

it("blocks nomination signing when Aadhaar is unverified", async () => {
  responses[`${memberBase}/nominations`] = { ...nominations, aadhaar_verified: false };
  renderPage(<NominationPage />);
  expect(await screen.findByText("Aadhaar verification is required before you can sign an e-Nomination.")).toBeTruthy();
  const form = screen.getByRole("form", { name: "New e-Nomination" });
  expect((within(form).getByRole("group", { name: "Nominee details" }) as HTMLFieldSetElement).disabled).toBe(true);
  fireEvent.submit(form); expect(ask).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
});

it("looks up UANs using mock OTP details and displays matches and delivery information", async () => {
  vi.mocked(command).mockResolvedValue({ data: { found: [{ uan, aadhaar_verified: true, latest_establishment: "Example establishment", status: "ACTIVE" }],
    sent_to: "******1234", note: "Mock lookup completed." }, meta: {} });
  renderPage(<NominationPage />);
  const section = (await screen.findByRole("heading", { name: "Know your UAN" })).closest("section")!;
  fill(section, "Name", "Member"); fill(section, "Date of birth", "1990-01-01"); fill(section, "Mobile last four digits", "1234"); fill(section, "Mock OTP", "123456");
  fireEvent.submit(section.querySelector("form")!);
  expect(await screen.findByText("Example establishment")).toBeTruthy(); expect(screen.getByText("Sent to: ******1234")).toBeTruthy();
  expect(command).toHaveBeenCalledWith("POST", "/api/v1/members/uan-lookups", { name: "Member", date_of_birth: "1990-01-01", mobile_last4: "1234", otp: "123456" });
  expect(ask).not.toHaveBeenCalled();
});

it("rejects the invalid mock lookup OTP 000000", async () => {
  renderPage(<NominationPage />);
  const section = (await screen.findByRole("heading", { name: "Know your UAN" })).closest("section")!;
  fill(section, "Name", "Member"); fill(section, "Date of birth", "1990-01-01"); fill(section, "Mobile last four digits", "1234"); fill(section, "Mock OTP", "000000");
  fireEvent.submit(section.querySelector("form")!);
  expect(await screen.findByRole("alert")).toBeTruthy(); expect(command).not.toHaveBeenCalled();
});

it("confirms auto-transfer without a body and binds the transfer ID and paise amount", async () => {
  renderPage(<ServicePage />);
  fireEvent.click(await screen.findByRole("button", { name: "Confirm auto-transfer AT-1" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${memberBase}/transfers/auto/AT-1/confirmations`, undefined, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "confirm-auto-transfer", resourceId: "AT-1", amountPaise: 123450 }));
});

it("shows auto-transfer eligibility reasons and history when no transfer is eligible", async () => {
  responses[`${memberBase}/transfers/auto`] = { primary_account_link_id: null, reasons: ["No primary member ID."], eligible: [],
    history: [{ transfer_id: "AT-OLD", state: "POSTED", from_account_link_id: "AL-OLD", to_account_link_id: "AL-2", amount_paise: 50000,
      confirmed_at: "2026-09-01", posted_at: "2026-09-02" }], note: "Mock auto-transfer." };
  renderPage(<ServicePage />);
  expect(await screen.findByText("No primary member ID.")).toBeTruthy(); expect(screen.getByText("AT-OLD")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Confirm auto-transfer/ })).toBeNull();
});

it("switches a claim to a verified bank with step-up bound to its ID and version", async () => {
  renderPage(<ClaimDetailPage />, "/member/claims/CLM-1");
  const button = await screen.findByRole("button", { name: "Switch bank with one-time code" });
  fireEvent.submit(button.closest("form")!);
  await waitFor(() => expect(command).toHaveBeenCalledWith("PUT", `${memberBase}/claims/CLM-1/bank-details`, banks.verified_accounts[0], { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "switch-claim-bank", resourceId: "CLM-1", resourceVersion: 7 }));
  expect(screen.getByText(claim.next_step)).toBeTruthy();
});

it("shows employer rejection and the returned next step, without offering a bank switch", async () => {
  responses[`${memberBase}/claims/CLM-1`] = { ...claim, state: "REJECTED_BY_EMPLOYER", next_step: "Review the employer's rejection note." };
  responses[`${memberBase}/claims/CLM-1/bank-details`] = { ...banks, switchable: false };
  renderPage(<ClaimDetailPage />, "/member/claims/CLM-1");
  expect(await screen.findByText("The bank account cannot be switched at this claim stage.")).toBeTruthy();
  expect(screen.getByText("Review the employer's rejection note.")).toBeTruthy();
  expect(screen.getByText("Rejected by employer")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Switch bank with one-time code" })).toBeNull();
});

it.each(["ATTEST", "REJECT"])("records a signatory claim decision %s with the claim ID and version", async (decision) => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.signatory" });
  renderPage(<MemberActionsPage />);
  const form = await screen.findByRole("form", { name: "Decide claim CLM-1" });
  fill(form, "Decision", decision); fill(form, "Decision note", "Checked employer records."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${employerBase}/claim-attestations/CLM-1/decisions`, { decision, note: "Checked employer records." }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "attest-claim", resourceId: "CLM-1", resourceVersion: 7 }));
});

it("allows owners to view claim attestations without a decision form", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.owner" });
  renderPage(<MemberActionsPage />);
  expect(await screen.findByText("Employer records required.")).toBeTruthy();
  expect(screen.queryByRole("form", { name: "Decide claim CLM-1" })).toBeNull();
  expect(ask).not.toHaveBeenCalled();
});

it("submits an exit correction using the UAN and presents it in signatory approvals", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.operator" });
  renderPage(<MemberActionsPage />);
  const form = await screen.findByRole("form", { name: "Exit correction" });
  fill(form, "UAN", uan); fill(form, "Member ID at this establishment", "AL-1"); fill(form, "Date of exit", "2026-08-31");
  fill(form, "Reason", "RETIREMENT"); fill(form, "Correction note", "Corrected using employer records."); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${employerBase}/members/${uan}/exit-corrections`, {
    account_link_id: "AL-1", date_of_exit: "2026-08-31", reason: "RETIREMENT", correction_note: "Corrected using employer records.",
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "correct-exit-employer", resourceId: uan }));
  cleanup();
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.signatory" });
  responses[`${employerBase}/approvals`] = [{ case_id: "CASE-1", subject_ref: uan, state: "CORRECTION_MARKED", version: 3,
    data: { account_link_id: "AL-1", date_of_exit: "2026-08-31", reason: "RETIREMENT", correction_note: "Corrected using employer records." } }];
  renderPage(<MemberActionsPage />);
  expect(await screen.findByRole("heading", { name: "Exit correction" })).toBeTruthy();
  expect(screen.getByText("Corrected using employer records.", { exact: false })).toBeTruthy();
  const decisionForm = screen.getByRole("group", { name: "Decision for CASE-1" }).closest("form")!;
  fireEvent.click(within(decisionForm).getByLabelText("Approve")); fill(decisionForm, "Note", "Correction verified."); fireEvent.submit(decisionForm);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${employerBase}/approvals/CASE-1/decisions`, { decision: "APPROVE", note: "Correction verified." }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenLastCalledWith(expect.objectContaining({ action: "approve-exit", resourceId: "CASE-1", resourceVersion: 3 }));
});

it("binds bulk exit upload to the establishment and preserves partial success results", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.operator" });
  vi.mocked(command).mockResolvedValue({ data: { lines: 2, accepted: 1, results: [
    { line: 1, status: "ACCEPTED", case_id: "CASE-1", uan }, { line: 2, status: "ERROR", error: "Member ID does not belong to this establishment." },
  ] }, meta: {} });
  renderPage(<MemberActionsPage />);
  const form = await screen.findByRole("form", { name: "Exit bulk upload" });
  const content = `uan,account_link_id,date_of_exit,reason\n${uan},AL-1,2026-08-31,CESSATION\n${uan},AL-INVALID,2026-08-31,RETIREMENT`;
  fill(form, "CSV content", content); fireEvent.submit(form);
  expect(await screen.findByText("Member ID does not belong to this establishment.")).toBeTruthy();
  expect(screen.getByText("Accepted")).toBeTruthy(); expect(screen.getByText("Could not process")).toBeTruthy();
  expect(command).toHaveBeenCalledWith("POST", `${employerBase}/members/exit-bulk-uploads`, { content }, { stepUpToken: "step-up-token" });
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "mark-exit-bulk", resourceId: "EST-1" }));
});

it("submits an employer Joint Declaration with mock member consent and step-up bound to the UAN", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.signatory" });
  renderPage(<JointDeclarations />);
  const form = await screen.findByRole("form", { name: "Employer-initiated JD" });
  fill(form, "UAN", uan); fill(form, "Parameter", "NAME"); fill(form, "Current value", "Old name"); fill(form, "Corrected value", "Correct name");
  fill(form, "Reason", "Corrected using supporting records."); fill(form, "Document reference (optional)", "DOC-1");
  fireEvent.click(within(form).getByLabelText("Member consent confirmed by Aadhaar OTP (mock)")); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${employerBase}/joint-declarations`, {
    uan, parameter: "NAME", current_value: "Old name", corrected_value: "Correct name", reason: "Corrected using supporting records.",
    document_ref: "DOC-1", member_consent: "MOCK_AADHAAR_OTP",
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "submit-joint-declaration-employer", resourceId: uan }));
});

it("does not show the employer Joint Declaration submission form to an owner", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "employer.owner" });
  renderPage(<JointDeclarations />);
  await screen.findByText("Nothing is waiting for your attestation.");
  expect(screen.queryByRole("form", { name: "Employer-initiated JD" })).toBeNull();
});
