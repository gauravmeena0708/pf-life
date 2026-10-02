import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { MonthlyReturn } from "./exempted/MonthlyReturn";
import { RankingsPage } from "./exempted/RankingsPage";
import { ExemptedPage } from "./office/ExemptedPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn(), newIdempotencyKey: () => "key-1" }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let responses: Record<string, unknown>;
beforeEach(() => { vi.clearAllMocks(); ask.mockResolvedValue("step-token"); responses = {};
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.exemption" });
  vi.mocked(api).mockImplementation(async (path) => { if (!(path in responses)) throw new Error(`Unexpected API path: ${path}`); return { data: responses[path], meta: {} }; });
  vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);
function show(page: ReactElement) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const parts = { transfer_before_due_date: 90, investment: 80, remittance: 70, interest_declared: 60, claim_settlement: 50, audit_of_accounts: 100 };
const flag = { flag_id: "TF-1", category: "A", code: "CLAIMS_LATE", text: "One claim was late", action: null };
const filed = { return_id: "TR-1", wage_month: "2026-09", version: 1, state: "FILED", score: 450, parts, flags: [flag], employees_opening: 2, joined: 0, left: 0, excluded: 0,
  contract_trust: 2, contract_elsewhere: 0, direct_exempted: 0, direct_unexempted: 0, international_workers: 0, disabled_workers: 0,
  pf_wages_paise: 100000, employee_share_paise: 12000, employer_share_paise: 12000, due_paise: 24000, transfers: [], interest_paid_paise: 0,
  claims_opening: 0, claims_received: 1, claims_within_days: 0, claims_beyond_days: 1, claims_pending: 0, pending_reasons: null,
  grievances_opening: 0, grievances_received: 0, grievances_disposed: 0, interest_rate_declared_bp: 825, investible_corpus_paise: 100000,
  invested_paise: 90000, accounts_audited: true, member_balances_total_paise: null };
const month = (() => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; })();   // the rankings open on last month
const ranking = { rank: 1, establishment_id: "EST-1", legal_name: "Demo Trust", office_id: "FO-1", wage_month: month, score: 450, flags: ["CLAIMS_LATE"] };

it("checks balance live and posts paise", async () => {
  responses["/api/v1/exempted/me/returns"] = { returns: [] }; show(<MonthlyReturn />);
  const form = screen.getByRole("form", { name: "File monthly return" });
  fireEvent.change(within(form).getByLabelText("Opening"), { target: { value: "2" } });
  expect(within(form).getByText(/does not balance/)).toBeTruthy();
  fireEvent.change(within(form).getByLabelText("Contract under the trust"), { target: { value: "2" } });
  expect(within(form).getByText(/balanced/)).toBeTruthy();
  for (const [label, value] of [["Wage month", "2026-09"], ["PF wages (₹)", "1000.50"], ["Employee share (₹)", "120.25"], ["Employer share (₹)", "80.10"], ["Interest declared (%)", "8.25"]]) fireEvent.change(within(form).getByLabelText(label), { target: { value } });
  fireEvent.submit(form);
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/exempted/me/returns", expect.objectContaining({ wage_month: "2026-09", employees_opening: 2, contract_trust: 2,
    pf_wages_paise: 100050, employee_share_paise: 12025, employer_share_paise: 8010, due_paise: 20035, interest_rate_declared_bp: 825,
    transfers: [], member_balances_total_paise: null, revised: false }), { idempotencyKey: "key-1" }));
});
it("shows score parts and category flags, muting superseded returns", async () => {
  responses["/api/v1/exempted/me/returns"] = { returns: [filed, { ...filed, return_id: "TR-0", version: 0, state: "SUPERSEDED", flags: [] }] }; show(<MonthlyReturn />);
  const current = await screen.findByLabelText("Return 2026-09 version 1");
  expect(within(current).getByText(/450\/600/)).toBeTruthy(); expect(within(current).getAllByRole("progressbar")).toHaveLength(6);
  expect(within(current).getByLabelText("Category A")).toBeTruthy();
  expect(screen.getByLabelText("Return 2026-09 version 0").className).toContain("trust-superseded");
});
it("shows office rankings and posts a step-up flag action without advice for A", async () => {
  responses[`/api/v1/office/exempted/rankings?month=${month}`] = { rankings: [ranking] };
  responses["/api/v1/office/exempted/EST-1/returns"] = { returns: [filed] }; show(<ExemptedPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Demo Trust" }));
  const form = await screen.findByRole("form", { name: "Action flag TF-1" });
  expect(within(form).queryByRole("option", { name: "Advice" })).toBeNull();
  fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "Issue notice" } }); fireEvent.submit(form);
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "action-trust-flag", resourceId: "TF-1" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/exempted/EST-1/flags/TF-1/actions",
    { action: "DIRECTION_TO_RECTIFY", note: "Issue notice" }, { stepUpToken: "step-token" }));
});
it("shows read-only HO ranking and routes both roles", async () => {
  responses[`/api/v1/office/exempted/rankings?month=${month}`] = { rankings: [ranking] }; show(<RankingsPage />);
  expect(await screen.findByText("Demo Trust")).toBeTruthy(); expect(screen.queryByRole("button", { name: "Demo Trust" })).toBeNull();
  expect(menusFor("ho.exemption")).toEqual([{ label: "Exempted establishments ranking", to: "/ho/exempted-rankings" }, { label: "Exemption proceedings", to: "/exemption-proceedings" }]);
  expect(homeFor("ho.exemption")).toBe("/ho/exempted-rankings"); expect(homeFor("fo.exemption")).toBe("/office/exempted");
  expect(menusFor("fo.exemption").flatMap((group) => group.items ?? [])).toContainEqual(expect.objectContaining({ label: "Monthly Return for Exempted Establishment", to: "/office/exempted#exempted-rankings-heading" }));
});
