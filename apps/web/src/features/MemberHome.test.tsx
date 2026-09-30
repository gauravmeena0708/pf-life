import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { api } from "../api/client";
import i18n from "../i18n";
import { MemberHomePage } from "./member/MemberHomePage";

vi.mock("../api/client", async (importOriginal) => ({ ...await importOriginal<typeof import("../api/client")>(), api: vi.fn() }));

const base = "/api/v1/members/me";
const responses: Record<string, unknown> = {
  [base]: { name: "Demo Member", uan: "1001", kyc: { aadhaar: "VERIFIED", pan: "VERIFIED", bank: "VERIFIED" } },
  [`${base}/service-history`]: { member_ids: [{ account_link_id: "OLD", establishment_name: "Old Works", date_of_joining: "2018-01-01",
    date_of_exit: "2023-01-31", last_contribution_month: "2022-12", transferred_to: null, status: "EXITED", mark_exit_allowed: false, primary: false }], total_service_months: 66 },
  [`${base}/claims/eligible-types`]: { accounts: [{ account_link_id: "OLD", balance: { total_paise: 120050 }, types: [{ claim_type: "ADVANCE", label: "Medical advance" }] }] },
  [`${base}/claims`]: [{ claim_id: "C1", claim_type: "ADVANCE", form_type: "31", amount_paise: 50000, state: "SUBMITTED",
    next_step: "Employer attestation needed", created_at: "2026-09-01" }],
  [`${base}/applications`]: [], [`${base}/nominations`]: { current: { state: "CURRENT" } },
  [`${base}/pension-eligibility-preview`]: { scenarios: [{ label: "At retirement", eligible: true, monthly_paise: 450000 }], note: "Illustrative" },
  [`${base}/passbook`]: { pending: [] },
};
let client: QueryClient;
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(api).mockImplementation(async (path) => ({ data: responses[path], meta: {} }));
});
afterEach(() => { cleanup(); client.clear(); vi.clearAllMocks(); });

function mount() {
  render(<QueryClientProvider client={client}><MemoryRouter><MemberHomePage /></MemoryRouter></QueryClientProvider>);
}

it("shows balances, next steps, nudges and all life events", async () => {
  mount();
  const savings = screen.getByRole("region", { name: "Your savings" });
  expect((await within(savings).findAllByText("₹1,200.50")).length).toBe(2);
  expect(screen.getByText("Demo Member")).toBeTruthy();
  expect(screen.getByRole("link", { name: /Move ₹1,200.50 from Old Works/ })).toBeTruthy();
  expect(screen.getByRole("link", { name: /Employer attestation needed Medical advance/ })).toHaveProperty("pathname", "/member/claims/C1");
  for (const title of ["I changed jobs", "I need money for illness, a house, education or a wedding", "I am leaving work",
    "I am retiring or want my pension", "Someone in my family has died", "Something in my record is wrong"]) {
    expect(screen.getByRole("heading", { name: title })).toBeTruthy();
  }
});

it("keeps the other sections visible when nominations fails", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === `${base}/nominations`) throw new Error("Nomination service unavailable");
    return { data: responses[path], meta: {} };
  });
  mount();
  expect((await screen.findAllByText("₹1,200.50")).length).toBe(2);
  expect(await screen.findByText("Error: Nomination service unavailable")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "What is pending" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "What do you want to do?" })).toBeTruthy();
});

it("renders the member home heading in Hindi and switches back to English", async () => {
  try {
    await act(async () => { await i18n.changeLanguage("hi"); });
    mount();
    expect(screen.getByRole("heading", { name: "आपकी भविष्य निधि एक नज़र में" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "मैंने नौकरी बदली है" })).toBeTruthy();
  } finally {
    await act(async () => { await i18n.changeLanguage("en"); });
  }
  expect(screen.getByRole("heading", { name: "Your PF at a glance" })).toBeTruthy();
});
