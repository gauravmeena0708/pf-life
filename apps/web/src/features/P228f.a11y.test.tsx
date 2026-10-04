import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { configureAxe } from "vitest-axe";
import { api } from "../api/client";
import "../i18n";
import { ClaimJourneyPage } from "./member/ClaimJourneyPage";
import { BankJourneyPage } from "./member/BankJourneyPage";
import { TransferJourneyPage } from "./member/TransferJourneyPage";
import { Stepper } from "../components/ui/Stepper";
import { ErrorSummary } from "../components/ui/ErrorSummary";
import { MoneyInput } from "../components/ui/MoneyInput";
import { SummaryList } from "../components/ui/SummaryList";
import { ConfirmationPanel } from "../components/ui/ConfirmationPanel";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: vi.fn(),
  command: vi.fn(),
}));

afterEach(cleanup);

const axe = configureAxe({
  rules: {
    "color-contrast": { enabled: false },
  },
});

const wrap = (node: ReactNode, initialEntries = ["/"]) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={initialEntries}>{node}</MemoryRouter>
    </QueryClientProvider>
  );

describe("P2.28f automated accessibility checks", () => {
  const eligibleTypesResponse = {
    accounts: [
      {
        account_link_id: "AL-0001",
        primary: true,
        balance: { employee_paise: 5000000, employer_paise: 5000000, total_paise: 10000000 },
        types: [
          {
            claim_type: "ILLNESS",
            form_type: "31",
            label: "Illness",
            plain_rule: "Up to 6 months basic wages or employee share with interest.",
            eligible: true,
            max_amount_paise: 5000000,
            reasons: [],
          },
          {
            claim_type: "FINAL_SETTLEMENT",
            form_type: "19",
            label: "Final settlement",
            plain_rule: "Full PF balance.",
            eligible: false,
            max_amount_paise: 0,
            reasons: ["Member is currently in service"],
            fixes: [
              {
                reason: "In service",
                fix: "Mark date of exit after leaving employment",
                link: "/member/service",
              },
            ],
          },
        ],
      },
      {
        account_link_id: "AL-0002",
        primary: false,
        balance: { employee_paise: 2000000, employer_paise: 2000000, total_paise: 4000000 },
        types: [
          {
            claim_type: "ILLNESS",
            form_type: "31",
            label: "Illness",
            plain_rule: "Up to 6 months wages.",
            eligible: false,
            max_amount_paise: 0,
            reasons: ["Account has a pending transfer"],
          },
        ],
      },
    ],
  };

  const employmentResponse = [
    {
      account_link_id: "AL-0001",
      establishment_name: "Demo Engineering Works",
      date_of_joining: "2024-01-01",
      date_of_exit: null,
      status: "ACTIVE",
    },
    {
      account_link_id: "AL-0002",
      establishment_name: "Previous Enterprise",
      date_of_joining: "2021-05-10",
      date_of_exit: "2023-12-31",
      status: "EXITED",
    },
  ];

  const memberProfileResponse = {
    member_id: "M-001",
    name: "Demo Member",
    bank: {
      ifsc: "SBIN0001234",
      account_last4: "9876",
    },
    kyc: {
      aadhaar: "VERIFIED",
      pan: "VERIFIED",
      bank: "VERIFIED",
    },
  };

  const kycResponse = {
    aadhaar: "VERIFIED",
    pan: "VERIFIED",
    bank: "VERIFIED",
    pan_masked: "ABCDE1234F",
    bank_ifsc: "SBIN0001234",
    bank_account_last4: "9876",
    requests: [],
  };

  const serviceHistoryResponse = {
    uan: "100000000007",
    primary_member_id: "AL-0009",
    total_service_months: 64,
    member_ids: [
      {
        account_link_id: "AL-0008",
        establishment_name: "Previous Enterprise",
        date_of_joining: "2021-05-10",
        date_of_exit: "2023-12-31",
        exit_marked_by: "EMPLOYER",
        last_contribution_month: "2023-12",
        transferred_to: null,
        status: "EXITED",
        service_months: 31,
        mark_exit_allowed: false,
        transfer_status: "NOT_TRANSFERRED",
        primary: false,
      },
      {
        account_link_id: "AL-0009",
        establishment_name: "Current Enterprise",
        date_of_joining: "2024-01-01",
        date_of_exit: null,
        exit_marked_by: null,
        last_contribution_month: "2026-09",
        transferred_to: null,
        status: "ACTIVE",
        service_months: 33,
        mark_exit_allowed: false,
        transfer_status: "CURRENT",
        primary: true,
      },
    ],
  };

  function mockEndpoints() {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/members/me/claims/eligible-types") {
        return { data: eligibleTypesResponse, meta: {} };
      }
      if (path === "/api/v1/members/me/employment-history") {
        return { data: employmentResponse, meta: {} };
      }
      if (path === "/api/v1/members/me") {
        return { data: memberProfileResponse, meta: {} };
      }
      if (path === "/api/v1/members/me/kyc") {
        return { data: kycResponse, meta: {} };
      }
      if (path === "/api/v1/members/me/service-history") {
        return { data: serviceHistoryResponse, meta: {} };
      }
      if (path === "/api/v1/members/me/account-status") {
        return { data: { uan: "10001", accounts: [] }, meta: {} };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });
  }

  describe("Claim journey accessibility", () => {
    it("has no violations at step 1", async () => {
      mockEndpoints();
      const { container } = wrap(<ClaimJourneyPage />, ["/member/claims/new"]);
      expect(await screen.findByText(/Demo Engineering Works · 2024 – now/)).toBeTruthy();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("has no violations at step 1 state (claim type selection)", async () => {
      mockEndpoints();
      const { container } = wrap(<ClaimJourneyPage />, ["/member/claims/new"]);

      const activeRadio = await screen.findByLabelText(/Demo Engineering Works/);
      fireEvent.click(activeRadio);
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      expect(await screen.findByRole("heading", { name: "What are you claiming for?" })).toBeTruthy();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("has no violations at Check your answers", async () => {
      mockEndpoints();
      const { container } = wrap(<ClaimJourneyPage />, ["/member/claims/new"]);

      // Step 1: select account and continue
      const activeRadio = await screen.findByLabelText(/Demo Engineering Works/);
      fireEvent.click(activeRadio);
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      // Step 2: select claim type and continue
      const claimRadio = await screen.findByLabelText(/Illness/);
      fireEvent.click(claimRadio);
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      // Step 3: enter amount and continue
      const amountInput = await screen.findByLabelText(/Amount in whole rupees/i);
      fireEvent.change(amountInput, { target: { value: "40000" } });
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      // Step 4: where it is paid
      await screen.findByRole("heading", { name: "Where it is paid" });
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      // Step 5: Check your answers
      await screen.findByRole("heading", { name: "Check your answers" });

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  describe("Bank journey accessibility", () => {
    it("has no violations with an error summary showing", async () => {
      mockEndpoints();
      const { container } = wrap(<BankJourneyPage />, ["/member/kyc/bank/new"]);

      await screen.findByRole("heading", { name: "Change your bank account" });
      // Trigger validation error on empty IFSC
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      expect(await screen.findByRole("alert")).toBeTruthy();
      expect(screen.getByRole("heading", { name: "There is a problem" })).toBeTruthy();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  describe("Transfer journey accessibility", () => {
    it("has no violations", async () => {
      mockEndpoints();
      const { container } = wrap(<TransferJourneyPage />, ["/member/service/transfer/new"]);

      expect(await screen.findByRole("heading", { name: "Which old account?" })).toBeTruthy();

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  describe("Shared UI components on their own", () => {
    it("Stepper has no violations", async () => {
      const { container } = render(
        <Stepper steps={["First step", "Second step", "Third step"]} current={1} />
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("ErrorSummary has no violations", async () => {
      const { container } = render(
        <ErrorSummary
          errors={[
            { field: "test-field-1", message: "First error message" },
            { field: "test-field-2", message: "Second error message" },
          ]}
        />
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("MoneyInput with an error has no violations", async () => {
      const { container } = render(
        <MoneyInput
          id="test-amount"
          label="Amount in rupees"
          hint="Up to 50,000"
          error="Amount is required"
          value={null}
          onChange={() => {}}
        />
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("SummaryList has no violations", async () => {
      const { container } = render(
        <SummaryList
          rows={[
            { key: "job", label: "Job", value: "Acme Corp", onChange: () => {} },
            { key: "amount", label: "Amount", value: "₹50,000" },
          ]}
        />
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("ConfirmationPanel has no violations", async () => {
      const { container } = render(
        <ConfirmationPanel
          title="Claim submitted"
          reference="CLM-987654"
          referenceLabel="Reference number"
        >
          <p>We have received your claim.</p>
        </ConfirmationPanel>
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});

it("fails on a real violation (the check is live, not a no-op)", async () => {
  const { container } = render(<div><img src="x.png" /><button type="button"></button></div>);
  const results = await axe(container);
  expect(results.violations.map((v) => v.id).sort()).toEqual(["button-name", "image-alt"]);
});
