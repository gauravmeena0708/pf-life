import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { ApiError, api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { CscPage } from "./csc/CscPage";
import { Form16A } from "./member/Form16A";
import { SecurityPage } from "./member/SecurityPage";
import { ClaimToolsPage } from "./office/ClaimToolsPage";
import { InoperativeSearchPage } from "./public/InoperativeSearchPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(),
}));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

const account = { account_link_id: "AL-1", name: "Demo Member", balance_paise: 625000, last_credit: "2021-03-31", verified: false, reactivated: false };
let responses: Record<string, unknown>;
let client: QueryClient;
beforeEach(() => {
  vi.clearAllMocks();
  responses = {
    "/api/v1/members/me": { member_id: "M-1", uan: "100000000001", mobile_masked: "******1234", email_masked: "m***@demo.test" },
    "/api/v1/members/me/sessions": [],
    "/api/v1/office/accounts/inoperative": { accounts: [account] },
    "/api/v1/public/demo-challenges": { challenge_id: "CH-1", prompt: "What is 2 + 3?" },
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.startsWith("/api/v1/members/me/tax/form-16a?")) return { data: { certificate_no: "16A/2025-26/0001/1", financial_year: "2025-26", section: "192A", note: "Illustrative/mock document; not valid for filing.",
      deductor: { name: "EPFO synthetic", tan: "DELE00000E", office_id: "RO-1" }, deductee: { name: "Demo Member", pan_masked: null, pan_status: "VERIFIED" },
      quarters: ["Q1", "Q2", "Q3", "Q4"].map((quarter) => ({ quarter, amount_paid_paise: 10000, tds_paise: 1000 })),
      totals: { amount_paid_paise: 40000, tds_paise: 4000 } }, meta: {} };
    if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`);
    return { data: responses[path], meta: {} };
  });
  vi.mocked(command).mockImplementation(async (_method, path) => ({ data: path.includes("uan-activations") ? { activated_at: "2026-09-30T10:00:00Z" }
    : path.includes("uan-allotments") ? { uan: "100000000002", next_step: "Ask your employer to link your member ID." }
    : path.includes("tds/computations") ? { acknowledgement: "26Q-ACK-1", deductees: [{ claim_id: "CLM-1", uan_masked: "********0001", paid_on: "2025-06-01", amount_paid_paise: 10000, tds_paise: 1000, pan_status: "VERIFIED" }], totals: { amount_paid_paise: 10000, tds_paise: 1000 }, note: "Illustrative/mock document; not valid for filing." }
    : path.includes("inoperative-accounts/searches") ? { matches: [{ search_ref: "REF-1", member_id_masked: "****AL-1", establishment_name: "Demo Works", last_credit_year: 2021 }], otp_sent_to: "the mobile on record", demo: { otp: "123456", otp_by_search_ref: { "REF-1": "123456" }, note: "demo only" } }
    : {}, meta: {} }));
  ask.mockResolvedValue("step-up-token");
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => { cleanup(); client.clear(); });
function page(element: ReactElement, role = "member") {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  render(<QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>);
}
function fill(label: string, value: string, root: HTMLElement = document.body) {
  fireEvent.change(within(root).getByLabelText(label), { target: { value } });
}
const problem = (type: string, title: string, detail: string, status = 409) => new ApiError({ type, title, detail, status });

it("renders Form 16A quarters, totals, parties and the illustrative note", async () => {
  page(<Form16A />);
  expect(await screen.findByText(/16A\/2025-26\/0001\/1/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "TDS certificate (Form 16A)" })).toBeTruthy();
  expect(screen.getByText("DELE00000E", { exact: false })).toBeTruthy();
  expect(screen.getByRole("row", { name: /Q4/ })).toBeTruthy();
  expect(screen.getByText("₹400.00")).toBeTruthy();
  expect(screen.getByText(/not valid for filing/)).toBeTruthy();
});
it("activates the prefilled UAN and displays the activation time", async () => {
  page(<SecurityPage />);
  expect((await screen.findByLabelText("UAN") as HTMLInputElement).value).toBe("100000000001");
  fill("OTP", "123456"); fireEvent.submit(screen.getByRole("button", { name: "Activate UAN" }).closest("form")!);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/members/uan-activations", { uan: "100000000001", otp: "123456" }));
  expect(await screen.findByText(/Activated at/)).toBeTruthy();
});
it("shows the activation 409 problem", async () => {
  vi.mocked(command).mockRejectedValueOnce(problem("/problems/already-active", "This UAN is already active", "Already activated."));
  page(<SecurityPage />); await screen.findByLabelText("UAN"); fill("OTP", "123456");
  fireEvent.submit(screen.getByRole("button", { name: "Activate UAN" }).closest("form")!);
  expect(await screen.findByText("Already activated.")).toBeTruthy();
});
it("sends the mock face token and shows the CSC allotment result", async () => {
  page(<CscPage />, "csc_operator");
  fill("Aadhaar number", "123456789012"); fill("Name", "Demo Member"); fill("Date of birth", "1990-01-01"); fill("Gender", "FEMALE"); fill("Mobile", "9876543210");
  fireEvent.click(screen.getByRole("button", { name: "Capture face (mock)" })); fireEvent.click(screen.getByRole("button", { name: "Allot UAN" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/members/uan-allotments", expect.objectContaining({ aadhaar: "123456789012", face_auth_token: "MOCK-FACE-MATCH" })));
  expect(await screen.findByText("100000000002")).toBeTruthy(); expect(screen.getByText("Aadhaar: ********9012")).toBeTruthy();
});
it("requires the second search step before showing a balance and sends CAPTCHA on both steps", async () => {
  page(<InoperativeSearchPage />, "public");
  fill("Name", "Demo Member"); fill("Date of birth", "1990-01-01"); fill("Establishment name", "Demo Works");
  fireEvent.click(screen.getByRole("button", { name: "Get one-use demo question" }));
  await screen.findByLabelText("What is 2 + 3?");
  fill("What is 2 + 3?", "5"); fireEvent.submit(screen.getByRole("form", { name: "Search for an inoperative account" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/public/inoperative-accounts/searches", expect.objectContaining({ challenge_id: "CH-1", answer: 5, establishment_query: "Demo Works" })));
  expect(await screen.findByText(/OTP sent to/)).toBeTruthy(); expect(screen.queryByText(/Balance:/)).toBeNull();
  fireEvent.click(screen.getByRole("radio")); fill("OTP", "123456");
  vi.mocked(command).mockResolvedValueOnce({ data: { member_id_masked: "****AL-1", balance_paise: 625000, next_step: "Visit your EPFO office." }, meta: { correlation_id: "", as_of: "" } });
  fireEvent.click(within(screen.getByRole("form", { name: "Verify selected account" })).getByRole("button", { name: "Get one-use demo question" }));
  await within(screen.getByRole("form", { name: "Verify selected account" })).findByLabelText("What is 2 + 3?");
  fill("What is 2 + 3?", "5", screen.getByRole("form", { name: "Verify selected account" }));
  fireEvent.submit(screen.getByRole("form", { name: "Verify selected account" }));
  await waitFor(() => expect(command).toHaveBeenLastCalledWith("POST", "/api/v1/public/inoperative-accounts/searches", { search_ref: "REF-1", otp: "123456", challenge_id: "CH-1", answer: 5 }));
  expect(await screen.findByText("Balance: ₹6,250.00")).toBeTruthy();
});
it("sends co-worker UANs as a list with the verification note", async () => {
  page(<ClaimToolsPage />, "fo.da_accounts"); fireEvent.click(await screen.findByRole("button", { name: "List" }));
  const form = await screen.findByRole("form", { name: "Verify AL-1 through co-workers" });
  fill("Co-worker UANs (comma separated)", "100000000001, 100000000002", form); fill("Verification note", "Worked together.", form); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/accounts/AL-1/crowdsource-verifications",
    { co_worker_uans: ["100000000001", "100000000002"], note: "Worked together." }));
});
it("binds reactivation step-up to account and balance, and shows above-your-band", async () => {
  vi.mocked(command).mockRejectedValueOnce(problem("/problems/above-your-band", "Above your approval band", "Forward to the APFC.", 403));
  page(<ClaimToolsPage />, "fo.ao"); fireEvent.click(await screen.findByRole("button", { name: "List" }));
  const form = await screen.findByRole("form", { name: "Reactivate AL-1" }); fill("Decision note", "Verified against record.", form); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "reactivate-account", resourceId: "AL-1", amountPaise: 625000 })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/accounts/AL-1/reactivations", { decision: "REACTIVATE", note: "Verified against record." }, { stepUpToken: "step-up-token" }));
  expect(await screen.findByText("Forward to the APFC.")).toBeTruthy();
});
it("renders the mock 26Q statement and the already-filed problem", async () => {
  page(<ClaimToolsPage />, "fo.da_accounts");
  const form = (await screen.findByRole("button", { name: "File mock statement" })).closest("form")!;
  fill("Financial year", "2025-26", form); fill("Quarter", "Q1", form); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/tds/computations", { financial_year: "2025-26", quarter: "Q1" }));
  expect(await screen.findByText("26Q-ACK-1")).toBeTruthy(); expect(screen.getByText("CLM-1")).toBeTruthy();
  vi.mocked(command).mockRejectedValueOnce(problem("/problems/already-filed", "TDS statement already filed", "Acknowledgement: 26Q-ACK-1"));
  fireEvent.submit(form); expect(await screen.findByText("Acknowledgement: 26Q-ACK-1")).toBeTruthy();
});
it("routes the CSC operator and exposes the new public and member links", () => {
  expect(homeFor("csc_operator")).toBe("/csc"); expect(menusFor("csc_operator")).toEqual([{ label: "UAN allotment", to: "/csc" }]);
  expect(menusFor("public").flatMap((group) => group.items ?? [])).toContainEqual(expect.objectContaining({ to: "/public/inoperative-accounts" }));
  expect(menusFor("member").flatMap((group) => group.items ?? [])).toContainEqual(expect.objectContaining({ to: "/member/claims#form-16a-heading" }));
});
