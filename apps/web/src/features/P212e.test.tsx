import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, getSession } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { BalanceSheetPage } from "./finance/BalanceSheetPage";
import { InvestmentsPage } from "./finance/InvestmentsPage";
import { BoardPacksPage } from "./finance/BoardPacksPage";

vi.mock("../api/client", async (importOriginal) => ({ ...await importOriginal<typeof import("../api/client")>(), api: vi.fn(), getSession: vi.fn() }));
const balance = { as_of: "2026-10-01", liabilities: [{ code: "AC01_EPF", name: "Members' provident fund accounts", amount_paise: 12345 }], assets: [{ code: "BANK_COLLECTION", name: "Bank — collections", amount_paise: 12345 }], total_liabilities_paise: 12345, total_assets_paise: 12345, balanced: true, journals_counted: 1, note: "Illustrative ledger." };
const totals = { book_value_paise: 10000, market_value_paise: 12000, unrealised_gain_paise: 2000 };
const investments = { as_of: "2026-10-01", funds: [{ fund: "EPF", totals, asset_classes: [{ asset_class: "EQUITY", ...totals, share_pct: 70, pattern_band: { min_pct: 45, max_pct: 65 }, flag: "ABOVE" }] }], totals, fund_managers: ["Manager A"], note: "Synthetic custody snapshots." };
const board = { generated_at: "2026-10-01T12:00:00Z", meeting: "CBT", note: "Aggregate facts.", sections: { contributions: { wage_months: 12, returns_filed: 4, returns_paid: 3, amount_paise: 10000 }, claims: { received: 3, settled: 2, rejected: 1, average_days_to_settle: 4, share_settled_within_20_days_pct: 100 }, grievances: { received: 2, resolved: 1, pending: 1, average_days_to_resolve: 5 }, investments: { as_of: "2026-10-01", funds: [{ fund: "EPF", totals }], totals } } };
let client: QueryClient;
beforeEach(() => { vi.clearAllMocks(); client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); vi.mocked(api).mockImplementation(async (path) => ({ data: path.includes("balance-sheet") ? balance : path.includes("board-packs") ? board : investments, meta: {} })); });
afterEach(() => { cleanup(); client.clear(); });
function renderPage(page: ReactElement, role: string) { vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role }); render(<QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }

it("shows balance sheet totals and balanced pill", async () => {
  renderPage(<BalanceSheetPage />, "gov.statutory_auditor");
  expect(await screen.findByText("Balanced")).toBeTruthy();
  expect(screen.getAllByText("₹123.45")).toHaveLength(4);
  expect(screen.getByText("Illustrative ledger.")).toBeTruthy();
});
it("shows an above-band investment flag in red", async () => {
  renderPage(<InvestmentsPage />, "ho.investment");
  const flag = await screen.findByText("Above band");
  expect(flag.classList.contains("alert")).toBe(true);
  expect(screen.getByText("45–65%")).toBeTruthy();
  expect(screen.getByText(/Manager A/)).toBeTruthy();
});
it.each([["gov.cbt", "CBT"], ["gov.ec", "EC"], ["gov.fiac", "FIAC"], ["ho.cpfc", "CBT"]])("defaults %s board pack to %s without personal identifiers", async (role, meeting) => {
  renderPage(<BoardPacksPage />, role);
  const select = await screen.findByLabelText("Meeting") as HTMLSelectElement;
  expect(select.value).toBe(meeting);
  await screen.findByText("Aggregate facts.");
  expect(vi.mocked(api).mock.calls.some(([path]) => path === `/api/v1/governance/board-packs?meeting=${meeting}`)).toBe(true);
  expect(screen.getByText("Aggregates only — no personal data")).toBeTruthy();
  expect(document.body.textContent).not.toMatch(/\b\d{12}\b|UAN[:\s-]*\d/i);
  expect(within(screen.getByRole("table")).getByText("EPF")).toBeTruthy();
});
it.each([
  ["gov.statutory_auditor", ["Balance sheet"], "/ho/finance/balance-sheet"],
  ["ho.investment", ["Investments"], "/ho/finance/investments"],
  ["gov.cbt", ["Board packs"], "/governance/board-packs"],
  ["gov.ec", ["Board packs"], "/governance/board-packs"],
  ["gov.fiac", ["Board packs", "Investments"], "/governance/board-packs"],
] as const)("routes %s through its finance or governance menu", (role, labels, home) => {
  expect(menusFor(role).map((item) => item.label)).toEqual(labels);
  expect(homeFor(role)).toBe(home);
});
it("adds finance and board items without replacing existing HO menus", () => {
  expect(menusFor("ho.fa_cao").map((item) => item.label ?? item.labelKey)).toEqual(["PMVBRY", "navigation.interest", "Record the interest rate", "Rule-change simulation", "Balance sheet", "Investments"]);
  expect(menusFor("ho.cpfc").at(-1)?.label).toBe("Board packs");
  expect(homeFor("ho.fa_cao")).toBe("/finance/interest");
  expect(homeFor("ho.cpfc")).toBe("/dashboards");
});
