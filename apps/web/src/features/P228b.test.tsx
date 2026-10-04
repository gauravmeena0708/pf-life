import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command } from "../api/client";
import "../i18n";
import { BankJourneyPage } from "./member/BankJourneyPage";
import { KycPage } from "./member/KycPage";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: vi.fn(),
  command: vi.fn(),
}));

afterEach(cleanup);

const wrap = (node: ReactNode, initialEntries = ["/member/kyc/bank/new"]) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>{node}</MemoryRouter>
    </QueryClientProvider>
  );

describe("P2.28b BankJourneyPage", () => {
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

  function mockEndpoints() {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/members/me") {
        return { data: memberProfileResponse, meta: {} };
      }
      if (path === "/api/v1/members/me/kyc") {
        return { data: kycResponse, meta: {} };
      }
      if (path === "/api/v1/members/me/account-status") {
        return { data: { uan: "10001", accounts: [] }, meta: {} };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });
  }

  let originalShowModal: PropertyDescriptor | undefined;
  let originalClose: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
    originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.open = true;
      },
    });
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      value(this: HTMLDialogElement) {
        this.open = false;
      },
    });
  });

  afterEach(() => {
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
  });

  it("shows the ErrorSummary and the field error for a bad IFSC", async () => {
    mockEndpoints();
    wrap(<BankJourneyPage />);

    // Step 1: Shows current bank on record
    expect(await screen.findByText(/Now: IFSC SBIN0001234, account ending 9876/)).toBeTruthy();

    const ifscInput = screen.getByLabelText(/IFSC/i) as HTMLInputElement;

    // Test empty IFSC validation
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "There is a problem" })).toBeTruthy();
    expect(screen.getAllByText("Enter an IFSC").length).toBeGreaterThanOrEqual(2);

    // Test bad format IFSC validation
    fireEvent.change(ifscInput, { target: { value: "INVALID_IFSC" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Both ErrorSummary link and field error show the message
    const errorMessages = screen.getAllByText(
      "Enter the IFSC as 4 letters, a zero, then 6 letters or numbers"
    );
    expect(errorMessages.length).toBeGreaterThanOrEqual(2);

    // Verify input uppercased
    fireEvent.change(ifscInput, { target: { value: "sbin0001234" } });
    expect(ifscInput.value).toBe("SBIN0001234");
  });

  it("refuses mismatched account numbers", async () => {
    mockEndpoints();
    wrap(<BankJourneyPage />);

    // Complete Step 1 with valid IFSC
    const ifscInput = await screen.findByLabelText(/IFSC/i);
    fireEvent.change(ifscInput, { target: { value: "SBIN0001234" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2: "Account number"
    expect(await screen.findByRole("heading", { name: "Account number" })).toBeTruthy();

    const accInput = screen.getByLabelText(/^Account number$/i);
    const accAgainInput = screen.getByLabelText(/Confirm account number/i);

    // Mismatched account numbers
    fireEvent.change(accInput, { target: { value: "123456784321" } });
    fireEvent.change(accAgainInput, { target: { value: "123456789999" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Error summary and field error
    expect(await screen.findByRole("alert")).toBeTruthy();
    const mismatchErrors = screen.getAllByText("The account numbers do not match");
    expect(mismatchErrors.length).toBeGreaterThanOrEqual(2);

    // User is still on Step 2
    expect(screen.getByRole("heading", { name: "Account number" })).toBeTruthy();
  });

  it("shows only 'ending 4321' on Check your answers and hides full account number", async () => {
    mockEndpoints();
    wrap(<BankJourneyPage />);

    // Step 1
    const ifscInput = await screen.findByLabelText(/IFSC/i);
    fireEvent.change(ifscInput, { target: { value: "SBIN0001234" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    const accInput = await screen.findByLabelText(/^Account number$/i);
    const accAgainInput = screen.getByLabelText(/Confirm account number/i);
    fireEvent.change(accInput, { target: { value: "123456784321" } });
    fireEvent.change(accAgainInput, { target: { value: "123456784321" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 3: Check your answers
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
    expect(screen.getByText("SBIN0001234")).toBeTruthy();
    expect(screen.getByText("ending 4321")).toBeTruthy();

    // Never show full number
    expect(screen.queryByText("123456784321")).toBeNull();
    expect(screen.queryByText(/123456784321/)).toBeNull();

    // Penny-drop note is visible
    expect(
      screen.getByText(
        /We check the account with a ₹1 penny-drop \(mock\), then your present employer approves it/i
      )
    ).toBeTruthy();

    // Change links exist
    const changeButtons = screen.getAllByRole("button", { name: /Change/i });
    expect(changeButtons.length).toBe(2);

    // Clicking Change for Account number goes to Step 2
    fireEvent.click(changeButtons[1]);
    expect(await screen.findByRole("heading", { name: "Account number" })).toBeTruthy();

    // Clicking Continue goes back to Step 3
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
  });

  it("submits, asks for the code, and shows ConfirmationPanel on PENDING_EMPLOYER", async () => {
    mockEndpoints();

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: {
            challenge_id: "CH-101",
            demo_otp: "987654",
            demo_notice: "Enter mock code 987654",
          },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/security/step-up-challenges/") && path.endsWith("/verifications")) {
        return {
          data: { step_up_token: "STEP-TOKEN-SUCCESS" },
          meta: {},
        };
      }
      if (path === "/api/v1/members/me/kyc/bank-accounts") {
        return {
          data: {
            request_id: "KYC-REQ-777",
            kyc_type: "BANK",
            masked_value: "SBIN0001234 · ending 4321",
            state: "PENDING_EMPLOYER",
            verification: {
              verifier: "penny-drop",
              verified: true,
            },
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<BankJourneyPage />);

    // Step 1
    fireEvent.change(await screen.findByLabelText(/IFSC/i), { target: { value: "SBIN0001234" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    fireEvent.change(await screen.findByLabelText(/^Account number$/i), { target: { value: "123456784321" } });
    fireEvent.change(screen.getByLabelText(/Confirm account number/i), { target: { value: "123456784321" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 3
    const submitBtn = await screen.findByRole("button", { name: "Submit" });
    fireEvent.click(submitBtn);

    // Step-up dialog
    expect(await screen.findByText("Enter mock code 987654")).toBeTruthy();
    expect(
      screen.getByText(
        "Change your bank account to the account ending 4321. It is checked by a penny-drop (mock) and then approved by your employer."
      )
    ).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/One-time code/i), { target: { value: "987654" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    // Confirmation panel
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Bank account checked" })).toBeTruthy();
    expect(screen.getByText("KYC-REQ-777")).toBeTruthy();
    expect(screen.getByText("Your request")).toBeTruthy();
    expect(
      screen.getByText(
        "Verified by penny-drop. Your employer approves it next; you will get a message. Until then claims are paid to the account now on record."
      )
    ).toBeTruthy();

    const kycLink = screen.getByRole("link", { name: "Back to KYC" });
    expect(kycLink.getAttribute("href")).toBe("/member/kyc");

    const claimLink = screen.getByRole("link", { name: "Start a claim" });
    expect(claimLink.getAttribute("href")).toBe("/member/claims/new");
  });

  it("shows reason and way back to step 2 on FAILED_VERIFICATION", async () => {
    mockEndpoints();

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: {
            challenge_id: "CH-102",
            demo_otp: "123456",
            demo_notice: "Enter mock code 123456",
          },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/security/step-up-challenges/") && path.endsWith("/verifications")) {
        return {
          data: { step_up_token: "STEP-TOKEN-FAILED" },
          meta: {},
        };
      }
      if (path === "/api/v1/members/me/kyc/bank-accounts") {
        return {
          data: {
            request_id: "KYC-REQ-888",
            kyc_type: "BANK",
            masked_value: "SBIN0001234 · ending 0000",
            state: "FAILED_VERIFICATION",
            verification: {
              verifier: "penny-drop",
              verified: false,
              reason: "Beneficiary account does not exist",
            },
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<BankJourneyPage />);

    // Step 1
    fireEvent.change(await screen.findByLabelText(/IFSC/i), { target: { value: "SBIN0001234" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    fireEvent.change(await screen.findByLabelText(/^Account number$/i), { target: { value: "123456780000" } });
    fireEvent.change(screen.getByLabelText(/Confirm account number/i), { target: { value: "123456780000" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 3
    fireEvent.click(await screen.findByRole("button", { name: "Submit" }));

    // Confirm step-up code
    expect(await screen.findByText("Enter mock code 123456")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/One-time code/i), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    // Stays on Step 3
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();

    // ErrorSummary shows the reason
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
      screen.getByText("The bank could not confirm this account: Beneficiary account does not exist")
    ).toBeTruthy();

    // Button "Enter another account number" takes user back to Step 2
    const enterAnotherBtn = screen.getByRole("button", { name: "Enter another account number" });
    fireEvent.click(enterAnotherBtn);

    // User is back on Step 2
    expect(await screen.findByRole("heading", { name: "Account number" })).toBeTruthy();
    expect(screen.getByLabelText(/^Account number$/i)).toBeTruthy();
  });

  it("renders Change your bank account link on KycPage to /member/kyc/bank/new", async () => {
    mockEndpoints();
    wrap(<KycPage />, ["/member/kyc"]);

    const link = await screen.findByRole("link", { name: "Change your bank account" });
    expect(link.getAttribute("href")).toBe("/member/kyc/bank/new");
  });
});
