import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import { menusFor } from "../data/navigation";
import "../i18n";
import { AuditsSection } from "./exempted/AuditsSection";
import { ProceedingView, type Proceeding } from "./exempted/ProceedingView";
import { ProceedingsQueue } from "./exempted/ProceedingsPage";
import { TrustPage } from "./exempted/TrustPage";
import { ExemptedPage } from "./office/ExemptedPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(), newIdempotencyKey: () => "key-1" }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let responses: Record<string, unknown>;
const proceeding = (stage: string, kind = "CANCELLATION", due: { step: string; role: string; due_by: string; overdue: boolean }[] = []): Proceeding => ({
  proceeding_id: "EXPR-1", establishment_id: "EST-1", kind, stage, open: true, due_by: "2026-09-01", overdue: true,
  history: [{ step: "SHOW_CAUSE_ISSUED", stage_after: "SHOW_CAUSE_ISSUED", actor_stakeholder: "fo.exemption", note: "Late claims", reference: "CE-77", at: "2026-09-01T10:00:00Z", form: "CE-1" }],
  what_is_due_next: due,
});
const next = (step: string, role: string) => ({ step, role, due_by: "2026-09-01", overdue: true });
beforeEach(() => { vi.clearAllMocks(); ask.mockResolvedValue("step-token"); responses = {};
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.exemption" });
  vi.mocked(api).mockImplementation(async (path) => { if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`); return { data: responses[path], meta: {} }; });
  vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);
function show(page: ReactElement) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const profile = { establishment: { establishment_id: "EST-1", legal_name: "Demo Trust" }, trust_name: "Demo Trust", kind: "PF", kind_description: "PF trust", pf_exempt: true, pension_exempt: false, edli_exempt: false,
  notification_no: "N-1", notification_date: "2020-01-01", effective_from: "2020-01-01", ended_on: null, status: "ACTIVE", conditions: [], note: "" };
function trustData(items: Proceeding[] = []) { responses["/api/v1/exempted/me/profile"] = profile; responses["/api/v1/exempted/me/annexure-k-requests"] = { requests: [] }; responses["/api/v1/exempted/me/returns"] = { returns: [] };
  responses["/api/v1/exempted/me/audits"] = []; responses["/api/v1/exempted/me/proceedings"] = items; }

it("checks audit arithmetic live and files paise with the opinion", async () => {
  responses["/api/v1/exempted/me/audits"] = []; show(<AuditsSection />);
  const form = screen.getByRole("form", { name: "File annual audited accounts" });
  for (const [label, value] of [["Financial year (YYYY-YY)", "2024-25"], ["Auditor", "Audit Co"], ["Auditor registration", "REG-1"], ["Opening corpus (₹)", "100.25"], ["Contributions (₹)", "20"], ["Interest credited (₹)", "5"], ["Claims paid (₹)", "10"], ["Other (+/−) (₹)", "-2"], ["Closing corpus (₹)", "113.25"]])
    fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  expect(within(form).getByText(/Balanced/)).toBeTruthy(); fireEvent.change(within(form).getByLabelText("Closing corpus (₹)"), { target: { value: "112" } });
  expect(within(form).getByRole("button", { name: "File annual audit" }).hasAttribute("disabled")).toBe(true);
  fireEvent.change(within(form).getByLabelText("Closing corpus (₹)"), { target: { value: "113.25" } }); fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/exempted/me/audits", expect.objectContaining({ financial_year: "2024-25", opening_corpus_paise: 10025, contributions_paise: 2000,
    interest_credited_paise: 500, claims_paid_paise: 1000, other_paise: -200, closing_corpus_paise: 11325, opinion: "UNQUALIFIED", revised: false })));
});
it("requires observations for a qualified audit", async () => {
  responses["/api/v1/exempted/me/audits"] = []; show(<AuditsSection />);
  const form = screen.getByRole("form", { name: "File annual audited accounts" }); fireEvent.change(within(form).getByLabelText("Auditor opinion"), { target: { value: "QUALIFIED" } }); fireEvent.submit(form);
  expect(await screen.findByText(/Observations are required/)).toBeTruthy(); expect(command).not.toHaveBeenCalled();
});
it("files surrender with the establishment step-up and pauses returns when exemption ends", async () => {
  trustData(); show(<TrustPage />); const form = await screen.findByRole("form", { name: "Surrender the exemption (Form SE-1)" });
  const day = new Date(); day.setDate(day.getDate() + 40); const date = day.toISOString().slice(0, 10);
  for (const [label, value] of [["Surrender date", date], ["Trustees' resolution reference", "BOT-1"], ["Corpus (₹)", "123.45"], ["Members", "12"]]) fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  fireEvent.click(within(form).getByLabelText("Employer's undertaking received")); fireEvent.click(within(form).getByLabelText("Employees' consent received")); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "surrender-exemption", resourceId: "EST-1" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/exempted/me/surrender-requests", { surrender_date: date, bot_resolution_ref: "BOT-1", employer_undertaking: true, employees_consent: true, corpus_paise: 12345, members: 12 }, { stepUpToken: "step-token" }));
  cleanup(); responses["/api/v1/exempted/me/profile"] = { ...profile, status: "SURRENDERED", ended_on: "2026-09-20" }; show(<TrustPage />);
  expect(await screen.findByText(/Returns stopped: the exemption ended on 2026-09-20/)).toBeTruthy(); expect(screen.queryByRole("form", { name: "File monthly return" })).toBeNull();
});
it("shows timeline and overdue action, then files a relinquishing reply", async () => {
  trustData([proceeding("SHOW_CAUSE_ISSUED", "CANCELLATION", [next("REPLY", "exempted.trust")])]); show(<TrustPage />);
  expect(await screen.findByText(/Form CE-1/)).toBeTruthy(); expect(screen.getByText(/Late claims/)).toBeTruthy(); expect(screen.getByText("Overdue")).toBeTruthy();
  const form = screen.getByRole("form", { name: "Reply to proceeding EXPR-1" }); fireEvent.change(within(form).getByLabelText("Reply to show-cause"), { target: { value: "We admit the lapse" } });
  fireEvent.click(within(form).getByLabelText("We admit the lapse and relinquish the exemption")); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "reply-show-cause", resourceId: "EXPR-1" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/exempted/me/proceedings/EXPR-1/replies", { reply: "We admit the lapse", relinquish: true }, { stepUpToken: "step-token" }));
});
it("opens a cancellation using an open category A flag and condition ground", async () => {
  const month = (() => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; })();
  responses[`/api/v1/office/exempted/rankings?month=${month}`] = { rankings: [{ rank: 1, establishment_id: "EST-1", legal_name: "Demo Trust", office_id: "FO-1", wage_month: month, score: 450, flags: ["CLAIMS_LATE"] }] };
  responses["/api/v1/office/exempted/EST-1/returns"] = { returns: [{ return_id: "TR-1", wage_month: month, version: 1, state: "FILED", score: 450, parts: {}, flags: [{ flag_id: "TF-1", category: "A", code: "CLAIMS_LATE", text: "Late", action: null }], transfers: [] }] };
  responses["/api/v1/office/exempted/EST-1/audits"] = []; responses["/api/v1/office/exempted/proceedings"] = []; show(<ExemptedPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Demo Trust" })); const form = await screen.findByRole("form", { name: "Open cancellation (show-cause notice, Form CE-1)" });
  fireEvent.click(within(form).getByLabelText(/Claims settled late|Claims late|TF-1/)); fireEvent.click(within(form).getByLabelText("Condition 25 breach"));
  fireEvent.change(within(form).getByLabelText(/Ground details.*TF-1/), { target: { value: "Claim delayed" } });
  fireEvent.change(within(form).getByLabelText("Ground details · Condition 25 breach"), { target: { value: "Condition unmet" } }); fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Issue CE-1" } }); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "show-cause-exemption", resourceId: "EST-1" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/exempted/EST-1/cancellation-proceedings", { grounds: [{ code: "CLAIMS_LATE", text: "Claim delayed" }, { code: "CONDITION_25", text: "Condition unmet" }], flag_ids: ["TF-1"], note: "Issue CE-1" }, { stepUpToken: "step-token" }));
});
it.each([
  ["fo.oic", "RELINQUISHED", "PERMIT_UNEXEMPTED", "exemption-step", "/api/v1/office/exempted/proceedings/EXPR-1/steps"],
  ["zo.acc", "AT_ZO", "FORWARD_TO_HO", "exemption-step", "/api/v1/office/exempted/proceedings/EXPR-1/steps"],
  ["ho.exemption", "SENT_TO_GOVERNMENT", "GOVERNMENT_NOTIFIED", "exemption-decision", "/api/v1/ho/exemptions/EST-1/decisions"],
])("posts %s action %s with the correct step-up", async (role, stage, step, action, path) => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role }); responses["/api/v1/office/exempted/proceedings"] = [proceeding(stage, "CANCELLATION", [next(step, role)])]; show(<ProceedingsQueue />);
  fireEvent.click(await screen.findByRole("button", { name: "EST-1" })); const form = screen.getByRole("form", { name: "Act on proceeding EXPR-1" });
  fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Approved" } });
  if (step === "GOVERNMENT_NOTIFIED") { fireEvent.change(within(form).getByLabelText("Notification number"), { target: { value: "N-99" } }); fireEvent.change(within(form).getByLabelText("Effective date"), { target: { value: "2026-10-15" } }); }
  if (step === "PERMIT_UNEXEMPTED") fireEvent.change(within(form).getByLabelText("Effective date"), { target: { value: "2026-10-15" } });
  fireEvent.submit(form); await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action, resourceId: role === "ho.exemption" ? "EST-1" : "EXPR-1" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", path, expect.objectContaining(role === "ho.exemption" ? { decision: step, reference: "N-99", date: "2026-10-15" } : { step }), { stepUpToken: "step-token" }));
});
it("offers zonal remand and the role menus", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "zo.acc" }); responses["/api/v1/office/exempted/proceedings"] = [proceeding("AT_ZO", "SURRENDER", [next("FORWARD_TO_HO", "zo.acc"), next("REMAND", "zo.acc")])]; show(<ProceedingsQueue />);
  fireEvent.click(await screen.findByRole("button", { name: "EST-1" })); expect(within(screen.getByRole("form", { name: "Act on proceeding EXPR-1" })).getByRole("option", { name: "Remand" })).toBeTruthy();
  expect(menusFor("ho.exemption")).toContainEqual({ label: "Exemption proceedings", to: "/exemption-proceedings" });
  expect(menusFor("zo.acc")).toContainEqual({ label: "Exemption proceedings", to: "/exemption-proceedings" });
  for (const role of ["fo.exemption", "fo.oic"]) expect(menusFor(role).flatMap((group) => group.items ?? [])).toContainEqual(expect.objectContaining({ label: "Exemption proceedings", to: "/exemption-proceedings" }));
  expect(screen.getAllByText("Overdue").length).toBeGreaterThan(1);
});
it("renders a proceeding history and next due step", () => { show(<ProceedingView proceeding={proceeding("AT_ZO", "CANCELLATION", [next("FORWARD_TO_HO", "zo.acc")])} />);
  expect(screen.getByText(/Form CE-1/)).toBeTruthy(); expect(screen.getByText(/Reference CE-77/)).toBeTruthy(); expect(screen.getByText("Overdue")).toBeTruthy(); });
