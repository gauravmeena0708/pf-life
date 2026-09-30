import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { ApiError, api, command, getMyPermissions, getSession } from "../api/client";
import { RoleNav } from "../components/RoleNav";
import { homeFor, memberMenus, menusFor } from "../data/navigation";
import "../i18n";
import { InternationalPage } from "./employer/InternationalPage";
import { MemberActionsPage } from "./employer/MemberActionsPage";
import { HigherPensionPage } from "./member/HigherPensionPage";
import { InternationalWorkerPage } from "./member/InternationalWorkerPage";
import { EdliPage } from "./office/EdliPage";
import { InternationalOfficePage } from "./office/InternationalOfficePage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(),
  api: vi.fn(), command: vi.fn(), getSession: vi.fn(), getMyPermissions: vi.fn(),
}));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const memberBase = "/api/v1/members/me";
const employerBase = "/api/v1/employers/me";
const internationalBase = "/api/v1/international/coc-applications";
const edliBase = "/api/v1/office/edli-claims";
const officeBase = "/api/v1/office/international/coc-applications";
const uan = "100000000001";
const option = { option_id: "HP-1", uan, account_link_id: "AL-1", state: "SUBMITTED", higher_wages_from: "2012-01",
  dues_paise: null, working: null, wages: [], rule_version: "demo", employer_note: null,
  submitted_at: "2026-09-30", validated_at: null, next_step: "Your employer validates the option.", name: "Member H", date_of_joining: "2010-01-01" };
const dues = { dues_paise: 123456, working: "Illustrative pension share above the ceiling.",
  wages: [{ month: "2012-01", wage_paise: 3000000, ceiling_paise: 650000, excess_paise: 2350000, dues_paise: 123456 }] };
const wages = "2012-01,30000.50";
const note = "Checked employer records.";
const reason = "Verified supporting records.";
const benefit = { amount_paise: 7654321, working: "Illustrative EDLI benefit.", filed_amount_paise: 5000000, version: 7 };
const application = { application_id: "COC-1", kind: "INITIAL", parent_id: null, uan, account_link_id: "AL-1",
  establishment_id: "EST-1", legal_name: "Demo establishment", country: "Germany", host_employer: "Host employer",
  posting_from: "2026-10-01", posting_to: "2027-09-30", state: "SUBMITTED", signed_upload: { filename: "signed.pdf", uploaded_at: "2026-09-30" },
  certificate_no: null, decision_reason: null, created_at: "2026-09-30", decided_at: null };
const agreements = { agreements: [{ country: "Germany", code: "DE", in_force_from: "2009-10-01", max_posting_months: 48,
  max_extension_months: 24, totalisation: true, note: "Illustrative terms." }], note: "Synthetic catalogue, illustrative terms." };
let responses: Record<string, unknown>;
let clients: QueryClient[];

beforeEach(() => {
  vi.clearAllMocks(); clients = [];
  responses = {
    [memberBase]: { uan }, [`${memberBase}/higher-pension-options`]: { options: [option], in_service_on: "2014-09-01", note: "Illustrative joint option." },
    [`${employerBase}/higher-pension-options`]: [option], [`${employerBase}/approvals`]: [], [`${employerBase}/transfer-requests`]: [],
    [`${employerBase}/claim-attestations`]: [], [`${employerBase}/pending-approvals`]: { items: [], note: "No pending approvals." },
    [`${employerBase}/members`]: [{ uan, name: "Member H", account_link_id: "AL-1", date_of_joining: "2010-01-01", date_of_exit: null }],
    [edliBase]: [{ claim_id: "EDLI-1", death_of_uan: uan, amount_paise: 5000000, version: 7, summary: "Death in service", working: "Filed working", service_months: 120 }],
    [officeBase]: [application], [internationalBase]: [application], ["/api/v1/international/agreements"]: agreements,
    [`${memberBase}/international`]: { uan, name: "International worker", international_worker: true, nationality: "Germany", passport_masked: "*****1234",
      employment: [{ account_link_id: "AL-1", establishment: "Demo establishment", date_of_joining: "2020-01-01", date_of_exit: null }],
      agreement: agreements.agreements[0], coverage: "Illustrative coverage from the service." },
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockImplementation(async (_method, path) => ({ data: path.endsWith("dues-previews") ? dues
    : path.endsWith("benefit-previews") ? benefit : application, meta: {} }));
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "member" });
  vi.mocked(getMyPermissions).mockResolvedValue({ data: { stakeholder: "employer.signatory", endpoints: [] } });
  ask.mockResolvedValue("step-up-token");
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });

function renderPage(page: ReactElement, role = "member") {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>);
}
function fill(form: HTMLElement, label: string, value: string) {
  fireEvent.change(within(form).getByLabelText(label), { target: { value } });
}
async function memberForm() {
  renderPage(<HigherPensionPage />);
  const form = await screen.findByRole("form", { name: "Submit higher-pension option" });
  await waitFor(() => expect((within(form).getByRole("group") as HTMLFieldSetElement).disabled).toBe(false));
  fill(form, "Higher wages from", "2012-01");
  fireEvent.click(within(form).getByLabelText("I declare that the option details are correct"));
  fireEvent.click(within(form).getByLabelText("I consent to adjustment of the higher-pension dues"));
  return form;
}
async function employerForm() {
  renderPage(<MemberActionsPage />, "employer.signatory");
  const form = await screen.findByRole("form", { name: "Validate higher-pension option HP-1" });
  fill(form, "Monthly wages (YYYY-MM,rupees per line)", wages); fill(form, "Validation note", note);
  return form;
}
async function edliForm() {
  renderPage(<EdliPage />, "fo.edli");
  const form = await screen.findByRole("form", { name: "Decide EDLI claim EDLI-1" });
  fill(form, "Verified average monthly wages (rupees)", "23456.78"); fill(form, "Decision reason", reason);
  return form;
}

it("submits a higher-pension option with step-up bound to the profile UAN", async () => {
  const form = await memberForm(); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${memberBase}/higher-pension-options`, {
    higher_wages_from: "2012-01", declaration: true, consent_to_dues_adjustment: true,
  }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "submit-higher-pension-option", resourceId: uan, summary: expect.any(String) });
});

it("shows detail and errors from a 422 higher-pension problem", async () => {
  vi.mocked(command).mockRejectedValue(new ApiError({ type: "/problems/validation", title: "Option cannot be submitted", status: 422,
    detail: "Please check the option.", errors: ["Member was not in service.", { field: "higher_wages_from", message: "Before joining." }] }));
  fireEvent.submit(await memberForm());
  expect(await screen.findByText("Please check the option.")).toBeTruthy();
  expect(screen.getByText("Member was not in service.")).toBeTruthy();
  expect(screen.getByText("higher_wages_from: Before joining.")).toBeTruthy();
});

it("requires both member declarations before requesting step-up", async () => {
  const form = await memberForm(); fireEvent.click(within(form).getByLabelText("I consent to adjustment of the higher-pension dues"));
  fireEvent.submit(form); expect(await screen.findByRole("alert")).toBeTruthy(); expect(ask).not.toHaveBeenCalled();
});

it("previews employer wages and binds validation to the option ID and previewed paise", async () => {
  const form = await employerForm(); fireEvent.click(within(form).getByRole("button", { name: "Preview dues" }));
  await within(form).findByText(dues.working);
  expect(command).toHaveBeenCalledWith("POST", `${employerBase}/higher-pension-options/HP-1/dues-previews`, { decision: "VALIDATE", wages, note });
  expect(ask).not.toHaveBeenCalled(); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${employerBase}/higher-pension-options/HP-1/validations`,
    { decision: "VALIDATE", wages, note }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "validate-higher-pension", resourceId: "HP-1", amountPaise: dues.dues_paise, summary: expect.any(String) });
});

it("rejects a higher-pension option without wages or an amount binding", async () => {
  const form = await employerForm(); fill(form, "Monthly wages (YYYY-MM,rupees per line)", "");
  fireEvent.click(within(form).getByRole("button", { name: "Reject" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${employerBase}/higher-pension-options/HP-1/validations`,
    { decision: "REJECT", note }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "validate-higher-pension", resourceId: "HP-1", summary: expect.any(String) });
});

it.each(["Monthly wages (YYYY-MM,rupees per line)", "Validation note"])("invalidates the dues preview when %s changes", async (label) => {
  const form = await employerForm(); fireEvent.click(within(form).getByRole("button", { name: "Preview dues" }));
  await within(form).findByText(dues.working); fill(form, label, label === "Validation note" ? "Updated note." : "2012-01,35000");
  expect((within(form).getByRole("button", { name: "Validate" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.submit(form); expect(await screen.findByRole("alert")).toBeTruthy(); expect(ask).not.toHaveBeenCalled();
});

it("works out EDLI from rupees and binds approval to the preview amount and version", async () => {
  const form = await edliForm(); fireEvent.click(within(form).getByRole("button", { name: "Work out benefit" }));
  await within(form).findByText(benefit.working);
  expect(command).toHaveBeenCalledWith("POST", `${edliBase}/EDLI-1/benefit-previews`, { average_monthly_wages_paise: 2345678 });
  expect(ask).not.toHaveBeenCalled(); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${edliBase}/EDLI-1/decisions`,
    { decision: "APPROVE", average_monthly_wages_paise: 2345678, reason }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "decide-edli", resourceId: "EDLI-1", resourceVersion: 7, amountPaise: benefit.amount_paise, summary: expect.any(String) });
});

it("rejects EDLI without verified wages or an amount binding", async () => {
  const form = await edliForm(); fill(form, "Verified average monthly wages (rupees)", "");
  fireEvent.click(within(form).getByRole("button", { name: "Reject" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${edliBase}/EDLI-1/decisions`, { decision: "REJECT", reason }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "decide-edli", resourceId: "EDLI-1", resourceVersion: 7, summary: expect.any(String) });
});

it("requires a fresh EDLI preview after wages change", async () => {
  const form = await edliForm(); fireEvent.click(within(form).getByRole("button", { name: "Work out benefit" }));
  await within(form).findByText(benefit.working); fill(form, "Verified average monthly wages (rupees)", "25000");
  expect((within(form).getByRole("button", { name: "Approve" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.submit(form); expect(await screen.findByRole("alert")).toBeTruthy(); expect(ask).not.toHaveBeenCalled();
});

it.each(["ISSUE", "REJECT"])("binds CoC decision %s to its application ID", async (decision) => {
  renderPage(<InternationalOfficePage />, "fo.iw");
  const form = await screen.findByRole("form", { name: "Decide CoC COC-1" });
  fill(form, "Decision", decision); fill(form, "Decision reason", reason); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${officeBase}/COC-1/decisions`, { decision, reason }, { stepUpToken: "step-up-token" }));
  expect(ask).toHaveBeenCalledWith({ action: "decide-coc", resourceId: "COC-1", summary: expect.any(String) });
});

it.each(["member", "employer", "edli", "coc"])("does not send the protected %s command when step-up is cancelled", async (kind) => {
  ask.mockResolvedValue(null);
  if (kind === "member") fireEvent.submit(await memberForm());
  if (kind === "employer") { const form = await employerForm(); fireEvent.click(within(form).getByRole("button", { name: "Reject" })); }
  if (kind === "edli") { const form = await edliForm(); fireEvent.click(within(form).getByRole("button", { name: "Reject" })); }
  if (kind === "coc") {
    renderPage(<InternationalOfficePage />, "fo.iw"); const form = await screen.findByRole("form", { name: "Decide CoC COC-1" });
    fill(form, "Decision", "ISSUE"); fill(form, "Decision reason", reason); fireEvent.submit(form);
  }
  await waitFor(() => expect(ask).toHaveBeenCalled()); expect(command).not.toHaveBeenCalled();
});

it.each(["employer", "edli", "coc"])("rejects a short %s decision note before step-up", async (kind) => {
  if (kind === "employer") { const form = await employerForm(); fill(form, "Validation note", "bad"); fireEvent.click(within(form).getByRole("button", { name: "Reject" })); }
  if (kind === "edli") { const form = await edliForm(); fill(form, "Decision reason", "bad"); fireEvent.click(within(form).getByRole("button", { name: "Reject" })); }
  if (kind === "coc") {
    renderPage(<InternationalOfficePage />, "fo.iw"); const form = await screen.findByRole("form", { name: "Decide CoC COC-1" });
    fill(form, "Decision", "ISSUE"); fill(form, "Decision reason", "bad"); fireEvent.submit(form);
  }
  expect(await screen.findByRole("alert")).toBeTruthy(); expect(ask).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
});

it("applies using the chosen member ID and agreement country without step-up", async () => {
  renderPage(<InternationalPage />, "employer.signatory");
  const form = await screen.findByRole("form", { name: "Apply for CoC" });
  await waitFor(() => expect((within(form).getByRole("group") as HTMLFieldSetElement).disabled).toBe(false));
  fill(form, "Member", "AL-1"); fill(form, "Agreement country", "Germany"); fill(form, "Host employer", "Host employer");
  fill(form, "Posting from", "2026-10-01"); fill(form, "Posting to", "2027-09-30"); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", internationalBase, {
    uan, account_link_id: "AL-1", country: "Germany", host_employer: "Host employer", posting_from: "2026-10-01", posting_to: "2027-09-30",
  })); expect(ask).not.toHaveBeenCalled();
});

it("uploads a signed PDF as base64 without step-up", async () => {
  responses[internationalBase] = [{ ...application, state: "AWAITING_SIGNED_UPLOAD", signed_upload: null }];
  renderPage(<InternationalPage />, "employer.signatory");
  const form = await screen.findByRole("form", { name: "Upload signed PDF COC-1" });
  const file = new File(["%PDF-1.4\nSigned"], "signed.pdf", { type: "application/pdf" });
  const input = within(form).getByLabelText("Signed PDF");
  fireEvent.change(input, { target: { files: [file] } });
  // jsdom's FormData does not collect a file assigned through a change event.
  const NativeFormData = globalThis.FormData;
  vi.spyOn(globalThis, "FormData").mockImplementation((element) => {
    const data = new NativeFormData(element); if (element === form) data.set("pdf", file); return data;
  });
  try {
    fireEvent.submit(form);
    await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${internationalBase}/COC-1/signed-uploads`, {
      filename: "signed.pdf", content_base64: btoa("%PDF-1.4\nSigned"),
    })); expect(ask).not.toHaveBeenCalled();
  } finally { vi.mocked(globalThis.FormData).mockRestore(); }
});

it("extends an issued certificate and displays a printable certificate without step-up", async () => {
  responses[internationalBase] = [{ ...application, state: "ISSUED", certificate_no: "CERT-1" }];
  responses[`${internationalBase}/COC-1/certificate`] = { certificate_no: "CERT-1", name: "Member H", uan,
    country: "Germany", host_employer: "Host employer", posting_from: "2026-10-01", posting_to: "2027-09-30",
    issued_at: "2026-09-30", issued_by_office: "RO-DEMO", verification_code: "VERIFY-1", text: "Illustrative certificate text." };
  renderPage(<InternationalPage />, "employer.signatory");
  const form = await screen.findByRole("form", { name: "Extend CoC COC-1" });
  fill(form, "Extension posting to", "2028-09-30"); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${internationalBase}/COC-1/extensions`, { posting_to: "2028-09-30" }));
  await waitFor(() => expect((screen.getByRole("button", { name: "View certificate" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "View certificate" }));
  expect(await screen.findByText("Illustrative certificate text.")).toBeTruthy(); expect(screen.getByText("VERIFY-1")).toBeTruthy();
  const print = vi.spyOn(window, "print").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Print certificate" })); expect(print).toHaveBeenCalled(); print.mockRestore();
  expect(ask).not.toHaveBeenCalled();
});

it("shows agreements to the HO unit without loading the decision queue", async () => {
  renderPage(<InternationalOfficePage />, "ho.iwu");
  expect(await screen.findByText(agreements.note)).toBeTruthy(); expect(screen.getByText("Germany")).toBeTruthy();
  expect(api).not.toHaveBeenCalledWith(officeBase); expect(screen.queryByRole("form")).toBeNull();
});

it("shows international worker employment, masked passport and service coverage", async () => {
  renderPage(<InternationalWorkerPage />, "member");
  expect(await screen.findByText("*****1234")).toBeTruthy(); expect(screen.getByText("Illustrative coverage from the service.")).toBeTruthy();
  expect(screen.getByText("Demo establishment")).toBeTruthy(); expect(screen.getByText("In service")).toBeTruthy();
});

it("shows a notice when a member is not recorded as an international worker", async () => {
  vi.mocked(api).mockRejectedValue(new ApiError({ type: "/problems/not-found", title: "Not found", status: 404,
    detail: "You are not recorded as an international worker" }));
  renderPage(<InternationalWorkerPage />, "member");
  expect(await screen.findByText("This service is available to members recorded as international workers.")).toBeTruthy();
  expect(api).toHaveBeenCalledWith(`${memberBase}/international`); expect(screen.queryByRole("alert")).toBeNull();
});

it("adds international worker coverage last in View only for international members", () => {
  const link = { label: "International worker coverage", to: "/international-worker" };
  const view = memberMenus(true).find((group) => group.label === "View")!;
  expect(view.items?.at(-1)).toEqual(link);
  expect(memberMenus(false).flatMap((group) => group.items ?? [])).not.toContainEqual(link);
  expect(memberMenus(false)).toBe(menusFor("member"));
});

it("keeps the member menu available while loading and then adds international coverage", async () => {
  let resolve!: (value: { data: { international_worker: boolean }; meta: Record<string, never> }) => void;
  vi.mocked(api).mockReturnValue(new Promise((done) => { resolve = done; }));
  renderPage(<RoleNav role="member" />);
  fireEvent.click(screen.getByRole("button", { name: /View/ }));
  expect(screen.getByRole("link", { name: "Profile" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "International worker coverage" })).toBeNull();
  resolve({ data: { international_worker: true }, meta: {} });
  expect(await screen.findByRole("link", { name: "International worker coverage" })).toHaveProperty("pathname", "/international-worker");
  expect(api).toHaveBeenCalledWith(memberBase);
});

it.each([
  ["fo.edli", "/office/edli-claims"], ["fo.iw", "/office/international"],
  ["ho.iwu", "/ho/agreements"], ["member", "/member/passbook"],
])("provides the %s landing path and a working menu link", (role, path) => {
  expect(homeFor(role)).toBe(path); expect(menusFor(role).some((group) => group.to?.startsWith(path) || group.items?.some((item) => item.to?.startsWith(path)))).toBe(true);
});

it.each([
  ["higher pension", <HigherPensionPage />, `${memberBase}/higher-pension-options`],
  ["EDLI", <EdliPage />, edliBase], ["CoC office", <InternationalOfficePage />, officeBase],
  ["CoC employer", <InternationalPage />, internationalBase], ["international worker", <InternationalWorkerPage />, `${memberBase}/international`],
])("does not load %s data for an unrelated role", async (_label, page, path) => {
  renderPage(page as ReactElement, "ho.security"); await screen.findByText(/This service is available/);
  expect(api).not.toHaveBeenCalledWith(path); expect(screen.queryByRole("form")).toBeNull();
});
