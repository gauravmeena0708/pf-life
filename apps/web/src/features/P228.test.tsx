import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command } from "../api/client";
import "../i18n";
import { ClaimJourneyPage } from "./member/ClaimJourneyPage";
import { parseRupees, groupIndian } from "../components/ui/MoneyInput";
import { ddmmyyyy, employmentLabel } from "../components/ui/format";

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  api: vi.fn(),
  command: vi.fn(),
}));

afterEach(cleanup);

const wrap = (node: ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/member/claims/new"]}>{node}</MemoryRouter>
    </QueryClientProvider>
  );

describe("P2.28 format and input helpers", () => {
  it("formats and parses whole rupees with Indian grouping (MoneyInput)", () => {
    expect(groupIndian(150000)).toBe("1,50,000");
    expect(groupIndian(0)).toBe("0");
    expect(groupIndian(10000000)).toBe("1,00,00,000");

    expect(parseRupees("1,50,000")).toBe(150000);
    expect(parseRupees("₹ 1,50,000")).toBe(150000);
    expect(parseRupees("50000")).toBe(50000);
    expect(parseRupees("0")).toBe(0);
    expect(parseRupees("")).toBeNull();
    expect(parseRupees("12.50")).toBeNull();
    expect(parseRupees("abc")).toBeNull();
  });

  it("formats dates as dd/mm/yyyy and creates employment labels (format.ts)", () => {
    expect(ddmmyyyy("2026-10-04")).toBe("04/10/2026");
    expect(ddmmyyyy(new Date(2026, 9, 4))).toBe("04/10/2026");
    expect(ddmmyyyy(null)).toBe("—");
    expect(ddmmyyyy(undefined)).toBe("—");

    const empActive = {
      establishment_name: "Demo Engineering Works",
      date_of_joining: "2024-01-01",
      date_of_exit: null,
    };
    expect(employmentLabel(empActive, "AL-0001", "now")).toBe("Demo Engineering Works · 2024 – now");

    const empExited = {
      establishment_name: "Previous Enterprise",
      date_of_joining: "2021-05-10",
      date_of_exit: "2023-12-31",
    };
    expect(employmentLabel(empExited, "AL-0002", "now")).toBe("Previous Enterprise · 2021 – 2023");

    expect(employmentLabel(undefined, "Member ID AL-0001", "now")).toBe("Member ID AL-0001");
  });
});

describe("P2.28 ClaimJourneyPage", () => {
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
            fixes: [{ reason: "In service", fix: "Mark date of exit after leaving employment", link: "/member/service" }],
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

  function mockEndpoints(overrides: { bankKyc?: string } = {}) {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/members/me/claims/eligible-types") {
        return { data: eligibleTypesResponse, meta: {} };
      }
      if (path === "/api/v1/members/me/employment-history") {
        return { data: employmentResponse, meta: {} };
      }
      if (path === "/api/v1/members/me") {
        return {
          data: {
            ...memberProfileResponse,
            kyc: {
              ...memberProfileResponse.kyc,
              bank: overrides.bankKyc ?? "VERIFIED",
            },
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });
  }

  it("walks through the 5 steps: employer label, validation, check answers, and step count", async () => {
    mockEndpoints();
    wrap(<ClaimJourneyPage />);

    // Step 1: Shows employer labels not raw IDs
    expect(await screen.findByText(/Demo Engineering Works · 2024 – now/)).toBeTruthy();
    expect(screen.getByText(/Previous Enterprise · 2021 – 2023/)).toBeTruthy();

    // Raw account_link_id is not the main label, only appears as muted "Member ID AL-0001"
    expect(screen.getByText("Member ID AL-0001")).toBeTruthy();
    expect(screen.getByText("Member ID AL-0002")).toBeTruthy();

    // Account 2 has no eligible claims; shown muted with reason and disabled radio
    expect(screen.getByText("No claim is open on this member ID")).toBeTruthy();
    const disabledRadio = document.getElementById("job-AL-0002") as HTMLInputElement;
    expect(disabledRadio.disabled).toBe(true);

    // Select account 1 and continue
    const activeRadio = document.getElementById("job-AL-0001") as HTMLInputElement;
    fireEvent.click(activeRadio);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2: "What for"
    expect(await screen.findByRole("heading", { name: "What are you claiming for?" })).toBeTruthy();
    expect(screen.getByText("Illness")).toBeTruthy();
    expect(screen.getByText("Not available now (1)")).toBeTruthy();
    expect(screen.getByText("What to do: Mark date of exit after leaving employment")).toBeTruthy();

    // Select "Illness" claim type and continue
    const claimRadio = document.getElementById("claim-ILLNESS") as HTMLInputElement;
    fireEvent.click(claimRadio);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 3: "How much"
    expect(await screen.findByRole("heading", { name: "How much do you want to claim?" })).toBeTruthy();

    // The stepper says "Step 3 of 5" on the amount step
    expect(screen.getByText("Step 3 of 5")).toBeTruthy();

    // Entering an amount above the maximum shows the ErrorSummary and the field error
    const amountInput = screen.getByLabelText(/Amount in whole rupees/i);
    fireEvent.change(amountInput, { target: { value: "60000" } }); // Max is ₹50,000 (5,000,000 paise)
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // ErrorSummary is displayed
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "There is a problem" })).toBeTruthy();
    // Both ErrorSummary link and field error message show the same message
    const errorMessages = screen.getAllByText(/Amount cannot exceed/);
    expect(errorMessages.length).toBeGreaterThanOrEqual(2);

    // Now enter a valid amount (₹40,000)
    fireEvent.change(amountInput, { target: { value: "40000" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 4: "Where it is paid"
    expect(await screen.findByRole("heading", { name: "Where it is paid" })).toBeTruthy();
    expect(screen.getByText(/SBIN0001234/)).toBeTruthy();
    expect(screen.getByText(/account ending 9876/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 5: "Check your answers" with the values
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
    expect(screen.getByText("Demo Engineering Works · 2024 – now")).toBeTruthy();
    expect(screen.getByText("Illness")).toBeTruthy();
    expect(screen.getByText("₹40,000.00")).toBeTruthy();
    expect(screen.getByText(/SBIN0001234 · account ending 9876/)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Change/ }).length).toBe(4);
  });

  it("blocks Continue and shows KYC link when bank is unverified", async () => {
    mockEndpoints({ bankKyc: "PENDING" });
    wrap(<ClaimJourneyPage />);

    // Step 1: Select job and continue
    const activeRadio = await screen.findByLabelText(/Demo Engineering Works/);
    fireEvent.click(activeRadio);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2: Select claim and continue
    const claimRadio = await screen.findByLabelText(/Illness/);
    fireEvent.click(claimRadio);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 3: Enter valid amount and continue
    const amountInput = await screen.findByLabelText(/Amount in whole rupees/i);
    fireEvent.change(amountInput, { target: { value: "10000" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 4: Where it is paid
    expect(await screen.findByRole("heading", { name: "Where it is paid" })).toBeTruthy();
    expect(screen.getByText("Your bank account is not verified yet")).toBeTruthy();

    const kycLink = screen.getByRole("link", { name: "Update bank details (KYC)" });
    expect(kycLink).toBeTruthy();
    expect(kycLink.getAttribute("href")).toBe("/member/kyc");

    const continueBtn = screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement;
    expect(continueBtn.disabled).toBe(true);
  });

  it("submits the claim, steps up, and renders ConfirmationPanel with next steps", async () => {
    mockEndpoints();

    const originalShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
    const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value(this: HTMLDialogElement) { this.open = true; },
    });
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      value(this: HTMLDialogElement) { this.open = false; },
    });

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/members/me/claims") {
        return {
          data: {
            claim_id: "CLM-0099",
            summary: "Illness claim of ₹30,000",
            amount_paise: 3000000,
            rules_applied: {
              route: "AUTO",
              approval_chain: [],
              settlement_sla_days: 20,
              rule_version: "2026.1",
              plain_rule: "Auto settled within SLA",
            },
            confirmation: {
              action: "create-claim",
              resource_id: "CLM-0099",
              resource_version: 1,
              amount_paise: 3000000,
            },
          },
          meta: {},
        };
      }
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: {
            challenge_id: "STEP-CH-1",
            demo_otp: "123456",
            demo_notice: "Enter mock code 123456",
          },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/security/step-up-challenges/") && path.endsWith("/verifications")) {
        return {
          data: {
            step_up_token: "STEP-TOKEN-XYZ",
          },
          meta: {},
        };
      }
      if (path === "/api/v1/members/me/claims/CLM-0099/confirmations") {
        return { data: { confirmed: true }, meta: {} };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    try {
      wrap(<ClaimJourneyPage />);

      // Step 1
      fireEvent.click(await screen.findByLabelText(/Demo Engineering Works/));
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      // Step 2
      fireEvent.click(await screen.findByLabelText(/Illness/));
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      // Step 3
      fireEvent.change(await screen.findByLabelText(/Amount in whole rupees/i), { target: { value: "30000" } });
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));

      // Step 4
      fireEvent.click(await screen.findByRole("button", { name: "Continue" }));

      // Step 5: Click Submit claim
      const submitBtn = await screen.findByRole("button", { name: "Submit claim" });
      fireEvent.click(submitBtn);

      // StepUpDialog shows
      expect(await screen.findByText("Enter mock code 123456")).toBeTruthy();
      fireEvent.change(screen.getByLabelText(/One-time code/i), { target: { value: "123456" } });
      fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

      // ConfirmationPanel is displayed
      expect(await screen.findByRole("status")).toBeTruthy();
      expect(screen.getByRole("heading", { name: "Claim submitted" })).toBeTruthy();
      expect(screen.getByText("CLM-0099")).toBeTruthy();
      expect(screen.getByText("It was approved automatically; the money is sent to your bank.")).toBeTruthy();
      expect(screen.getByText(/Expect it by/)).toBeTruthy();

      const trackLink = screen.getByRole("link", { name: "Track this claim" });
      expect(trackLink.getAttribute("href")).toBe("/member/claims/CLM-0099");

      const backLink = screen.getByRole("link", { name: "Back to my claims" });
      expect(backLink.getAttribute("href")).toBe("/member/claims");

      expect(screen.getByRole("button", { name: "Print or save receipt" })).toBeTruthy();
    } finally {
      if (originalShowModal) {
        Object.defineProperty(HTMLDialogElement.prototype, "showModal", originalShowModal);
      } else {
        Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
      }
      if (originalClose) {
        Object.defineProperty(HTMLDialogElement.prototype, "close", originalClose);
      } else {
        Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
      }
    }
  });
});
