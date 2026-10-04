import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command } from "../api/client";
import "../i18n";
import { PayrollProvidersPage } from "./employer/PayrollProvidersPage";
import { PayRunsPage } from "./employer/PayRunsPage";

vi.mock("../api/client", async (original) => {
  const actual = await original<typeof import("../api/client")>();
  const apiMock = vi.fn();
  return {
    ...actual,
    api: apiMock,
    command: vi.fn(),
    getSession: vi.fn(async () => apiMock("/auth/session")),
  };
});

afterEach(cleanup);

const wrap = (node: ReactNode, initialEntries = ["/employer/payroll-providers"]) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>{node}</MemoryRouter>
    </QueryClientProvider>
  );

describe("P2.22 Payroll Software & Pay Runs", () => {
  let originalShowModal: PropertyDescriptor | undefined;
  let originalClose: PropertyDescriptor | undefined;

  beforeEach(() => {
    vi.clearAllMocks();
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

  it("authorise asks for the code and lists the provider", async () => {
    let authorisedList: Array<{
      grant_id: string;
      provider_id: string;
      name: string;
      scopes: string[];
      status: "ACTIVE" | "REVOKED";
      granted_at: string;
    }> = [];

    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/auth/session") {
        return { authenticated: true, stakeholder: "employer.owner" };
      }
      if (path === "/api/v1/employers/me/payroll-providers") {
        return {
          data: {
            available: [{ provider_id: "PP-DEMO-1", name: "Demo Payroll Services" }],
            authorised: authorisedList,
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: {
            challenge_id: "CH-101",
            demo_otp: "123456",
            demo_notice: "Enter mock code 123456",
          },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/security/step-up-challenges/") && path.endsWith("/verifications")) {
        return {
          data: { step_up_token: "STEP-UP-AUTH-TOKEN" },
          meta: {},
        };
      }
      if (path === "/api/v1/employers/me/payroll-providers/authorisations") {
        authorisedList = [
          {
            grant_id: "GRANT-001",
            provider_id: "PP-DEMO-1",
            name: "Demo Payroll Services",
            scopes: ["payroll.submit"],
            status: "ACTIVE",
            granted_at: "2026-08-01T10:00:00Z",
          },
        ];
        return {
          data: {
            grant_id: "GRANT-001",
            provider_id: "PP-DEMO-1",
            name: "Demo Payroll Services",
            scopes: ["payroll.submit"],
            status: "ACTIVE",
            granted_at: "2026-08-01T10:00:00Z",
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<PayrollProvidersPage />);

    // Available provider is listed
    expect(await screen.findByText("Demo Payroll Services")).toBeTruthy();
    expect(screen.getByText("PP-DEMO-1")).toBeTruthy();

    const authButton = await screen.findByRole("button", { name: "Authorise" });
    fireEvent.click(authButton);

    // Step-up challenge dialog asks for one-time code
    expect(await screen.findByText("Enter mock code 123456")).toBeTruthy();
    expect(
      screen.getByText(/Authorise Demo Payroll Services to submit payroll runs directly/i)
    ).toBeTruthy();

    const otpInput = screen.getByLabelText(/One-time code/i);
    fireEvent.change(otpInput, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    // Provider is now listed under authorised providers
    await waitFor(() => {
      expect(screen.getByText("Send pay runs")).toBeTruthy();
    });
    expect(screen.getByText("GRANT-001")).toBeTruthy();
  });

  it("revoke needs a reason", async () => {
    let authorisedList: Array<{
      grant_id: string;
      provider_id: string;
      name: string;
      scopes: string[];
      status: "ACTIVE" | "REVOKED";
      granted_at: string;
    }> = [
      {
        grant_id: "GRANT-001",
        provider_id: "PP-DEMO-1",
        name: "Demo Payroll Services",
        scopes: ["payroll.submit"],
        status: "ACTIVE",
        granted_at: "2026-08-01T10:00:00Z",
      },
    ];

    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/auth/session") {
        return { authenticated: true, stakeholder: "employer.owner" };
      }
      if (path === "/api/v1/employers/me/payroll-providers") {
        return {
          data: {
            available: [{ provider_id: "PP-DEMO-1", name: "Demo Payroll Services" }],
            authorised: authorisedList,
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });

    let revokedReason = "";
    vi.mocked(command).mockImplementation(async (method, path, body) => {
      if (path === "/api/v1/security/step-up-challenges") {
        return {
          data: {
            challenge_id: "CH-REVOKE",
            demo_otp: "654321",
            demo_notice: "Enter mock code 654321",
          },
          meta: {},
        };
      }
      if (path.startsWith("/api/v1/security/step-up-challenges/") && path.endsWith("/verifications")) {
        return {
          data: { step_up_token: "STEP-UP-REVOKE-TOKEN" },
          meta: {},
        };
      }
      if (path === "/api/v1/employers/me/payroll-providers/authorisations/GRANT-001/revocations") {
        revokedReason = (body as { reason: string }).reason;
        authorisedList = [
          {
            grant_id: "GRANT-001",
            provider_id: "PP-DEMO-1",
            name: "Demo Payroll Services",
            scopes: ["payroll.submit"],
            status: "REVOKED",
            granted_at: "2026-08-01T10:00:00Z",
          },
        ];
        return {
          data: {
            grant_id: "GRANT-001",
            status: "REVOKED",
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<PayrollProvidersPage />);

    expect(await screen.findByText("GRANT-001")).toBeTruthy();
    expect(screen.getAllByText("Demo Payroll Services").length).toBeGreaterThanOrEqual(1);

    const revokeButton = await screen.findByRole("button", { name: "Revoke" });

    // Click revoke with empty reason -> validation error requiring reason
    fireEvent.click(revokeButton);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
      screen.getAllByText("Enter a revocation reason between 5 and 300 characters.").length
    ).toBeGreaterThanOrEqual(1);

    // Enter a valid reason
    const reasonInput = screen.getByLabelText(/Reason for revocation/i);
    fireEvent.change(reasonInput, { target: { value: "Switching to our in-house payroll module" } });

    // Now submit revocation
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

    // Step-up challenge asks for code
    expect(await screen.findByText("Enter mock code 654321")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/One-time code/i), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(revokedReason).toBe("Switching to our in-house payroll module");
    });
  });

  it("the pay runs page sums are shown and the responsive table has labels", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/auth/session") {
        return { authenticated: true, stakeholder: "employer.owner" };
      }
      if (path === "/api/v1/employers/me") {
        return {
          data: { legal_name: "Acme Corp", status: "ACTIVE", your_permissions: ["ecr.prepare"] },
          meta: {},
        };
      }
      if (path === "/api/v1/employers/me/pay-runs?wage_month=2026-08") {
        return {
          data: {
            wage_month: "2026-08",
            runs: [
              {
                pay_run_id: "PR-01",
                wage_month: "2026-08",
                run_ref: "RUN-AUG-15",
                pay_date: "2026-08-15",
                state: "ACCEPTED",
                totals: { gross_paise: 5000000, epf_wages_paise: 4000000, rows: 2 },
              },
              {
                pay_run_id: "PR-02",
                wage_month: "2026-08",
                run_ref: "RUN-AUG-31",
                pay_date: "2026-08-31",
                state: "ACCEPTED",
                totals: { gross_paise: 7000000, epf_wages_paise: 6000000, rows: 2 },
              },
            ],
            members: [
              {
                uan: "100000000001",
                name: "RAHUL SHARMA",
                runs: 2,
                gross_paise: 7000000,
                epf_wages_paise: 6000000,
                eps_wages_paise: 4000000,
                edli_wages_paise: 6000000,
                ncp_days: 0,
              },
              {
                uan: "100000000002",
                name: "PRIYA VERMA",
                runs: 2,
                gross_paise: 5000000,
                epf_wages_paise: 4000000,
                eps_wages_paise: 3000000,
                edli_wages_paise: 4000000,
                ncp_days: 1,
              },
            ],
            can_make_ecr: true,
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });

    wrap(<PayRunsPage />, ["/employer/pay-runs?month=2026-08"]);

    // Check sums are shown
    expect(await screen.findByText("Monthly summary")).toBeTruthy();
    expect(screen.getByText("Total pay runs")).toBeTruthy();
    expect(screen.getByText("Total members")).toBeTruthy();
    expect(screen.getByText("Total gross wages")).toBeTruthy();
    expect(screen.getByText("Total EPF wages")).toBeTruthy();

    const metricValues = Array.from(document.querySelectorAll(".payroll-metric-value")).map(
      (el) => el.textContent
    );
    expect(metricValues).toContain("2");
    expect(metricValues).toContain("₹1,20,000.00");
    expect(metricValues).toContain("₹1,00,000.00");

    // Check members table has responsive-table class and every td has data-label
    const tables = document.querySelectorAll("table.responsive-table");
    expect(tables.length).toBeGreaterThanOrEqual(1);

    const membersTable = tables[tables.length - 1];
    const cells = membersTable.querySelectorAll("tbody td");
    expect(cells.length).toBeGreaterThan(0);
    cells.forEach((td) => {
      const dataLabel = td.getAttribute("data-label");
      expect(dataLabel).toBeTruthy();
      expect(dataLabel?.trim().length).toBeGreaterThan(0);
    });
  });

  it("making the ECR shows the confirmation with the filing", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/auth/session") {
        return { authenticated: true, stakeholder: "employer.owner" };
      }
      if (path === "/api/v1/employers/me") {
        return {
          data: { legal_name: "Acme Corp", status: "ACTIVE", your_permissions: ["ecr.prepare"] },
          meta: {},
        };
      }
      if (path === "/api/v1/employers/me/pay-runs?wage_month=2026-08") {
        return {
          data: {
            wage_month: "2026-08",
            runs: [
              {
                pay_run_id: "PR-01",
                wage_month: "2026-08",
                run_ref: "RUN-AUG-15",
                pay_date: "2026-08-15",
                state: "ACCEPTED",
                totals: { gross_paise: 5000000, epf_wages_paise: 4000000, rows: 1 },
              },
            ],
            members: [
              {
                uan: "100000000001",
                name: "RAHUL SHARMA",
                runs: 1,
                gross_paise: 5000000,
                epf_wages_paise: 4000000,
                eps_wages_paise: 3000000,
                edli_wages_paise: 4000000,
                ncp_days: 0,
              },
            ],
            can_make_ecr: true,
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });

    vi.mocked(command).mockImplementation(async (method, path) => {
      if (path === "/api/v1/employers/me/pay-runs/2026-08/ecr-drafts") {
        return {
          data: {
            filing: {
              filing_id: "ECR-DRAFT-202608-777",
              wage_month: "2026-08",
              state: "VALIDATED",
            },
            validation_report: { valid: true },
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected command ${method} ${path}`);
    });

    wrap(<PayRunsPage />, ["/employer/pay-runs?month=2026-08"]);

    const makeEcrButton = await screen.findByRole("button", {
      name: "Make the ECR from these pay runs",
    });
    fireEvent.click(makeEcrButton);

    // Confirmation panel with filing reference and validation state
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByText("ECR draft created from pay runs")).toBeTruthy();
    expect(screen.getByText("ECR-DRAFT-202608-777")).toBeTruthy();
    expect(screen.getByText("VALIDATED")).toBeTruthy();

    const link = screen.getByRole("link", { name: "Go to ECR to approve and pay" });
    expect(link.getAttribute("href")).toBe("/employer/ecr");
  });

  it("the reason shown when it cannot be made", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/auth/session") {
        return { authenticated: true, stakeholder: "employer.owner" };
      }
      if (path === "/api/v1/employers/me") {
        return {
          data: { legal_name: "Acme Corp", status: "ACTIVE", your_permissions: ["ecr.prepare"] },
          meta: {},
        };
      }
      if (path === "/api/v1/employers/me/pay-runs?wage_month=2026-08") {
        return {
          data: {
            wage_month: "2026-08",
            runs: [],
            members: [],
            can_make_ecr: false,
            reason: "No accepted pay runs found for wage month 2026-08.",
          },
          meta: {},
        };
      }
      throw new Error(`Unexpected api call to ${path}`);
    });

    wrap(<PayRunsPage />, ["/employer/pay-runs?month=2026-08"]);

    expect(
      await screen.findByText("No accepted pay runs found for wage month 2026-08.")
    ).toBeTruthy();

    expect(
      screen.queryByRole("button", { name: "Make the ECR from these pay runs" })
    ).toBeNull();
  });
});
