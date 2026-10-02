import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api } from "../api/client";
import "../i18n";
import { ClaimsPage } from "./member/ClaimsPage";
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn() }));
afterEach(cleanup);

it("opens the claim form filled in from an offer (P2.21)", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/members/me/claims/eligible-types") return { data: { rule_version: "demo", illustrative_only: true, auto_settlement_limit_paise: 0, accounts: [
      { account_link_id: "AL-0006", balance: { employee_paise: 60000, employer_paise: 60050, total_paise: 120050 }, types: [
        { claim_type: "FINAL_SETTLEMENT", form_type: "19", label: "Final settlement", plain_rule: "", eligible: true, max_amount_paise: 120050, reasons: [] }] }] }, meta: {} };
    if (path === "/api/v1/members/me/claims") return { data: [], meta: {} };
    throw new Error("not available");
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={["/member/claims?account=AL-0006&type=FINAL_SETTLEMENT&amount=1200"]}><ClaimsPage /></MemoryRouter></QueryClientProvider>);
  const amount = await screen.findByDisplayValue("1200");                         // the amount, filled in
  expect(amount).toBeTruthy();
  const option = document.querySelector('input[type="radio"][value="AL-0006:FINAL_SETTLEMENT"]') as HTMLInputElement;
  expect(option.checked).toBe(true);
});
