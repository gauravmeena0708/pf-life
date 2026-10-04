import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, ApiError } from "../api/client";
import "../i18n";
import { TransferJourneyPage } from "./member/TransferJourneyPage";
import { ServicePage } from "./member/ServicePage";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: vi.fn(),
  command: vi.fn(),
}));

afterEach(cleanup);

const wrap = (node: ReactNode, initialEntries = ["/member/service/transfer/new"]) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>{node}</MemoryRouter>
    </QueryClientProvider>
  );

interface MemberIdFixture {
  account_link_id: string;
  establishment_name: string;
  date_of_joining: string;
  date_of_exit: string | null;
  exit_marked_by?: string | null;
  last_contribution_month?: string | null;
  transferred_to?: string | null;
  status: string;
  service_months: number;
  mark_exit_allowed: boolean;
  transfer_status: string;
  primary?: boolean;
}

interface ServiceHistoryFixture {
  uan: string;
  primary_member_id?: string | null;
  total_service_months?: number;
  member_ids: MemberIdFixture[];
}

describe("P2.28c TransferJourneyPage", () => {
  const serviceHistoryResponse: ServiceHistoryFixture = {
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

  const eligibleTypesResponse = {
    accounts: [
      {
        account_link_id: "AL-0008",
        balance: {
          employee_paise: 3000000,
          employer_paise: 2000000,
          total_paise: 5000000,
        },
      },
      {
        account_link_id: "AL-0009",
        balance: {
          employee_paise: 6000000,
          employer_paise: 4000000,
          total_paise: 10000000,
        },
      },
    ],
  };

  function mockEndpoints(overrides?: {
    serviceHistory?: ServiceHistoryFixture;
    eligibleTypes?: typeof eligibleTypesResponse | { accounts: [] };
  }) {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/api/v1/members/me/service-history") {
        return { data: overrides?.serviceHistory ?? serviceHistoryResponse, meta: { correlation_id: "c1", as_of: "2026-10-04" } };
      }
      if (path === "/api/v1/members/me/claims/eligible-types") {
        return { data: overrides?.eligibleTypes ?? eligibleTypesResponse, meta: { correlation_id: "c2", as_of: "2026-10-04" } };
      }
      if (path === "/api/v1/members/me/applications") {
        return { data: [], meta: { correlation_id: "c3", as_of: "2026-10-04" } };
      }
      if (path === "/api/v1/members/me/transfers/auto") {
        return { data: { primary_account_link_id: null, reasons: [], note: "", eligible: [], history: [] }, meta: { correlation_id: "c4", as_of: "2026-10-04" } };
      }
      if (path === "/api/v1/members/me/transfer-legs") {
        return { data: { transfers: [] }, meta: { correlation_id: "c5", as_of: "2026-10-04" } };
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

  it("shows old accounts by employer and shows ErrorSummary when continuing without a choice", async () => {
    mockEndpoints();
    wrap(<TransferJourneyPage />);

    // Step 1: Heading and Stepper
    expect(await screen.findByRole("heading", { name: "Which old account?" })).toBeTruthy();
    expect(screen.getByText("Step 1 of 3")).toBeTruthy();
    expect(screen.getByText("Old account")).toBeTruthy();
    expect(screen.getByText("Current account")).toBeTruthy();
    expect(screen.getByText("Check your answers")).toBeTruthy();

    // Old account shown by employer · years, not raw ID as main label
    expect(screen.getByText("Previous Enterprise · 2021 – 2023")).toBeTruthy();
    expect(screen.getByText("2 years 7 months")).toBeTruthy();
    expect(screen.getByText(/about ₹50,000.00/i)).toBeTruthy();
    expect(screen.getByText("Member ID AL-0008")).toBeTruthy();

    // Details accordion "Why move it?"
    expect(screen.getByText("Why move it?")).toBeTruthy();
    expect(
      screen.getByText(
        "One account keeps your service together for the pension and avoids withdrawing small balances."
      )
    ).toBeTruthy();

    // Click Continue without selecting an account
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // ErrorSummary is displayed with field link
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "There is a problem" })).toBeTruthy();
    const errorLinks = screen.getAllByText("Choose an old account to continue");
    expect(errorLinks.length).toBeGreaterThanOrEqual(1);

    // Click the old account radio and continue
    const radio = document.getElementById("from-AL-0008") as HTMLInputElement;
    fireEvent.click(radio);
    expect(radio.checked).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Successfully transitioned to Step 2
    expect(await screen.findByRole("heading", { name: "Into which account?" })).toBeTruthy();
  });

  it("shows the exit explanation with its link and already transferred explanation when none available", async () => {
    mockEndpoints({
      serviceHistory: {
        uan: "100000000007",
        member_ids: [
          {
            account_link_id: "AL-0001",
            establishment_name: "Current Enterprise",
            date_of_joining: "2024-01-01",
            date_of_exit: null,
            exit_marked_by: null,
            last_contribution_month: "2026-09",
            transferred_to: null,
            status: "ACTIVE",
            service_months: 20,
            mark_exit_allowed: false,
            transfer_status: "CURRENT",
            primary: true,
          },
          {
            account_link_id: "AL-0002",
            establishment_name: "Unmarked Enterprise",
            date_of_joining: "2021-01-01",
            date_of_exit: null,
            exit_marked_by: null,
            last_contribution_month: "2023-12",
            transferred_to: null,
            status: "ACTIVE",
            service_months: 36,
            mark_exit_allowed: true,
            transfer_status: "NOT_TRANSFERRED",
            primary: false,
          },
          {
            account_link_id: "AL-0003",
            establishment_name: "Transferred Enterprise",
            date_of_joining: "2018-01-01",
            date_of_exit: "2020-12-31",
            exit_marked_by: "EMPLOYER",
            last_contribution_month: "2020-12",
            transferred_to: "AL-0001",
            status: "EXITED",
            service_months: 36,
            mark_exit_allowed: false,
            transfer_status: "TRANSFERRED",
            primary: false,
          },
        ],
      },
    });

    wrap(<TransferJourneyPage />);

    expect(await screen.findByRole("heading", { name: "Which old account?" })).toBeTruthy();
    expect(screen.getByText("No previous member IDs are available to transfer.")).toBeTruthy();

    // Exit not marked explanation with link to mark exit
    expect(screen.getByText(/Your exit from Unmarked Enterprise is not marked yet/)).toBeTruthy();
    const markExitLinks = screen.getAllByRole("link", { name: "Mark your exit" });
    expect(markExitLinks.length).toBeGreaterThanOrEqual(1);
    expect(markExitLinks[0].getAttribute("href")).toBe("/member/service#exit-heading");

    // Already transferred explanation
    expect(screen.getByText(/Already moved to AL-0001/)).toBeTruthy();

    // Continue button is disabled
    const continueBtn = screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement;
    expect(continueBtn.disabled).toBe(true);
  });

  it("preselects the only current account and allows checking answers with Change navigation", async () => {
    mockEndpoints();
    wrap(<TransferJourneyPage />);

    // Step 1: Select old account and continue
    fireEvent.click(await screen.findByLabelText(/Previous Enterprise/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2: "Into which account?"
    expect(await screen.findByRole("heading", { name: "Into which account?" })).toBeTruthy();
    expect(screen.getByText("Step 2 of 3")).toBeTruthy();

    // Current account is preselected
    const currentRadio = document.getElementById("to-AL-0009") as HTMLInputElement;
    expect(currentRadio).toBeTruthy();
    expect(currentRadio.checked).toBe(true);
    expect(screen.getByText("Current Enterprise · 2024 – now")).toBeTruthy();
    expect(screen.getByText("This is your current account")).toBeTruthy();

    // Continue to Step 3
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 3: "Check your answers"
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
    expect(screen.getByText("Step 3 of 3")).toBeTruthy();

    // SummaryList rows
    expect(screen.getByText("Previous Enterprise · 2021 – 2023")).toBeTruthy();
    expect(screen.getByText("Current Enterprise · 2024 – now")).toBeTruthy();
    expect(screen.getAllByText("About to move").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("about ₹50,000.00 will move")).toBeTruthy();

    // Mandatory notice
    expect(
      screen.getByText(
        "Your present employer attests the request, then your regional office checks and approves it. Your service and balance move together; you will get a message at each step."
      )
    ).toBeTruthy();

    // Test Change buttons
    const changeButtons = screen.getAllByRole("button", { name: /Change/i });
    expect(changeButtons.length).toBe(3);

    // Clicking Change for "From" row takes user back to Step 1
    fireEvent.click(changeButtons[0]);
    expect(await screen.findByRole("heading", { name: "Which old account?" })).toBeTruthy();

    // Navigating forward again
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Into which account?" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();

    // Clicking Change for "Into" row takes user to Step 2
    fireEvent.click(screen.getAllByRole("button", { name: /Change/i })[1]);
    expect(await screen.findByRole("heading", { name: "Into which account?" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
  });

  it("omits 'About to move' row on Check your answers when balance is missing", async () => {
    mockEndpoints({
      eligibleTypes: { accounts: [] },
    });
    wrap(<TransferJourneyPage />);

    // Step 1
    fireEvent.click(await screen.findByLabelText(/Previous Enterprise/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));

    // Step 3
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
    expect(screen.queryByText("About to move")).toBeNull();
    expect(screen.queryByText(/will move/)).toBeNull();
  });

  it("submits transfer, steps up with challenge, and displays ConfirmationPanel with case reference and three steps", async () => {
    mockEndpoints();

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: {
            challenge_id: "CH-T1",
            demo_otp: "654321",
            demo_notice: "Enter mock code 654321",
          },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/security/step-up-challenges/") && path.endsWith("/verifications")) {
        return {
          data: { step_up_token: "STEP-TOKEN-VALID" },
          meta: {},
        };
      }
      if (path === "/api/v1/members/me/transfers") {
        return {
          data: {
            case_id: "CASE-FORM13-888",
            state: "SUBMITTED",
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<TransferJourneyPage />);

    // Step 1
    fireEvent.click(await screen.findByLabelText(/Previous Enterprise/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));

    // Step 3
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
    const sendBtn = screen.getByRole("button", { name: "Send the request" });
    fireEvent.click(sendBtn);

    // StepUpDialog is triggered
    expect(await screen.findByText("Enter mock code 654321")).toBeTruthy();
    expect(
      screen.getByText(
        "Move the PF of Previous Enterprise into your account with Current Enterprise. Your present employer attests it, then your regional office approves it."
      )
    ).toBeTruthy();

    // Confirm step-up code
    fireEvent.change(screen.getByLabelText(/One-time code/i), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    // Confirmation panel shown
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Transfer requested" })).toBeTruthy();
    expect(screen.getByText("Your request")).toBeTruthy();
    expect(screen.getByText("CASE-FORM13-888")).toBeTruthy();

    // Command verification
    expect(command).toHaveBeenCalledWith(
      "POST",
      "/api/v1/members/me/transfers",
      {
        from_account_link_id: "AL-0008",
        to_account_link_id: "AL-0009",
        attesting_employer: "PRESENT",
      },
      { stepUpToken: "STEP-TOKEN-VALID" }
    );

    // Three next steps as an ordered list
    expect(screen.getByText("Employer attests the request")).toBeTruthy();
    expect(screen.getByText("Regional office approves it")).toBeTruthy();
    expect(screen.getByText("The balance appears in your current account")).toBeTruthy();

    // Navigation links
    const trackLink = screen.getByRole("link", { name: "Track it on your service history" });
    expect(trackLink.getAttribute("href")).toBe("/member/service#transfer-status-heading");

    const backLink = screen.getByRole("link", { name: "Back to service history" });
    expect(backLink.getAttribute("href")).toBe("/member/service");
  });

  it("keeps answers intact when step-up dialog is cancelled", async () => {
    mockEndpoints();

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: {
            challenge_id: "CH-T2",
            demo_otp: "112233",
            demo_notice: "Enter mock code 112233",
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<TransferJourneyPage />);

    // Step 1
    fireEvent.click(await screen.findByLabelText(/Previous Enterprise/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));

    // Step 3
    fireEvent.click(await screen.findByRole("button", { name: "Send the request" }));

    // Dialog appears
    expect(await screen.findByText("Enter mock code 112233")).toBeTruthy();

    // Cancel dialog
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    // Stays on Step 3 with answers intact
    expect(await screen.findByRole("heading", { name: "Check your answers" })).toBeTruthy();
    expect(screen.getByText("Previous Enterprise · 2021 – 2023")).toBeTruthy();
    expect(screen.getByText("Current Enterprise · 2024 – now")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send the request" })).toBeTruthy();
  });

  it("blocks Step 2 if member has no current account to move into", async () => {
    mockEndpoints({
      serviceHistory: {
        uan: "100000000007",
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
        ],
      },
    });

    wrap(<TransferJourneyPage />);

    // Step 1
    fireEvent.click(await screen.findByLabelText(/Previous Enterprise/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    expect(await screen.findByRole("heading", { name: "Into which account?" })).toBeTruthy();
    expect(screen.getByText("You have no current account to move it into")).toBeTruthy();

    // Continue is disabled
    const continueBtn = screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement;
    expect(continueBtn.disabled).toBe(true);
  });

  it("displays server error in ErrorSummary if transfer command fails", async () => {
    mockEndpoints();

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: { challenge_id: "CH-T3", demo_otp: "123456", demo_notice: "Enter mock code 123456" },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/security/step-up-challenges/") && path.endsWith("/verifications")) {
        return { data: { step_up_token: "STEP-TOKEN-VALID" }, meta: {} };
      }
      if (path === "/api/v1/members/me/transfers") {
        throw new ApiError({
          type: "/problems/transfer-conflict",
          title: "Transfer already in progress",
          detail: "A transfer is already pending for this member ID",
          status: 409,
        });
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<TransferJourneyPage />);

    // Step 1
    fireEvent.click(await screen.findByLabelText(/Previous Enterprise/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Step 2
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));

    // Step 3
    fireEvent.click(await screen.findByRole("button", { name: "Send the request" }));

    // Step-up
    expect(await screen.findByText("Enter mock code 123456")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/One-time code/i), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    // ErrorSummary shows server error
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("A transfer is already pending for this member ID")).toBeTruthy();
  });

  it("renders 'Move an old account step by step' link on ServicePage to /member/service/transfer/new", async () => {
    mockEndpoints();
    wrap(<ServicePage />, ["/member/service"]);

    const link = await screen.findByRole("link", { name: "Move an old account step by step" });
    expect(link.getAttribute("href")).toBe("/member/service/transfer/new");
  });
});
