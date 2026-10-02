import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import "../i18n";
import { EmployerProceedingsPage } from "./employer/ProceedingsPage";

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  api: vi.fn(), command: vi.fn(), getSession: vi.fn(),
}));

let responses: Record<string, unknown>;
const as = (stakeholder: string) => vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder });

beforeEach(() => {
  vi.clearAllMocks();
  responses = {};
  vi.mocked(api).mockImplementation(async (path) => ({ data: responses[path], meta: {} }));
  vi.mocked(command).mockResolvedValue({ data: {}, meta: {} });
});
afterEach(cleanup);

function show(page: ReactElement) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const baseProceeding = (extra = {}) => ({
  case_id: "CMP-1",
  diary_no: "EPR/RO-DEMO-01/2026/0001",
  dispute: "DUES",
  period_from: "2025-04",
  period_to: "2025-09",
  officer_rank: "APFC",
  state: "ORDERED",
  summons: [],
  daily_orders: [],
  submissions: [],
  order: {
    kind: "ORDER",
    at: "2026-10-02T10:00:00Z",
    detail: { total_paise: 4500000, ex_parte: false, demand_id: "D7A-CMP-1", text: "ORDER UNDER SECTION 7A" },
  },
  orders: [{
    kind: "ORDER",
    at: "2026-10-02T10:00:00Z",
    detail: { total_paise: 4500000, ex_parte: false, demand_id: "D7A-CMP-1", text: "ORDER UNDER SECTION 7A" },
  }],
  applications: [],
  ...extra,
});

it("review form posts the right body", async () => {
  as("employer.owner");
  responses["/api/v1/employers/me/proceedings"] = [baseProceeding()];
  show(<EmployerProceedingsPage />);

  const form = await screen.findByRole("form", { name: /Apply for a review/ });
  expect(screen.getByText("Within 45 days of the order. A review is not an appeal: it lies only on these grounds.")).toBeTruthy();

  fireEvent.change(within(form).getByLabelText("Grounds"), { target: { value: "ERROR_APPARENT" } });
  fireEvent.change(within(form).getByLabelText("Text"), { target: { value: "Arithmetic error in schedule" } });
  fireEvent.change(within(form).getByLabelText(/Documents/), { target: { value: "recomputation.pdf, muster.pdf" } });
  fireEvent.click(within(form).getByRole("button", { name: "Submit" }));

  await waitFor(() => expect(command).toHaveBeenCalledWith(
    "POST",
    "/api/v1/employers/me/proceedings/CMP-1/applications",
    {
      kind: "REVIEW_7B",
      grounds: "ERROR_APPARENT",
      text: "Arithmetic error in schedule",
      documents: ["recomputation.pdf", "muster.pdf"],
    },
  ));
  expect(await screen.findByText("Your application is on the record")).toBeTruthy();
});

it("offers set-aside option only for an ex-parte order", async () => {
  as("employer.owner");
  responses["/api/v1/employers/me/proceedings"] = [baseProceeding({
    order: { kind: "ORDER", at: "2026-10-02T10:00:00Z", detail: { total_paise: 4500000, ex_parte: false, demand_id: "D7A-CMP-1", text: "ORDER" } },
  })];
  show(<EmployerProceedingsPage />);

  const form1 = await screen.findByRole("form", { name: /Apply for a review/ });
  expect(within(form1).queryByRole("option", { name: /set aside/i })).toBeNull();

  cleanup();
  responses["/api/v1/employers/me/proceedings"] = [baseProceeding({
    order: { kind: "ORDER", at: "2026-10-02T10:00:00Z", detail: { total_paise: 4500000, ex_parte: true, demand_id: "D7A-CMP-1", text: "ORDER" } },
  })];
  show(<EmployerProceedingsPage />);

  const form2 = await screen.findByRole("form", { name: /Apply for a review/ });
  expect(within(form2).getByRole("option", { name: /set aside/i })).toBeTruthy();

  fireEvent.change(within(form2).getByLabelText("Kind"), { target: { value: "SET_ASIDE" } });
  expect(screen.getByText("Within 3 months of the order.")).toBeTruthy();
  expect(within(form2).getByRole("option", { name: "The notice was not duly served" })).toBeTruthy();
  expect(within(form2).getByRole("option", { name: "A sufficient cause prevented appearance" })).toBeTruthy();
  expect(within(form2).queryByRole("option", { name: /New and important evidence/ })).toBeNull();

  fireEvent.change(within(form2).getByLabelText("Grounds"), { target: { value: "NOT_SERVED" } });
  fireEvent.change(within(form2).getByLabelText("Text"), { target: { value: "Notice mailed to closed branch" } });
  fireEvent.click(within(form2).getByRole("button", { name: "Submit" }));

  await waitFor(() => expect(command).toHaveBeenCalledWith(
    "POST",
    "/api/v1/employers/me/proceedings/CMP-1/applications",
    {
      kind: "SET_ASIDE",
      grounds: "NOT_SERVED",
      text: "Notice mailed to closed branch",
      documents: [],
    },
  ));
});

it("hides the application form while an application is pending", async () => {
  as("employer.owner");
  responses["/api/v1/employers/me/proceedings"] = [baseProceeding({
    applications: [{
      kind: "APPLICATION",
      at: "2026-10-03T10:00:00Z",
      detail: { application_id: "APP-01", kind: "REVIEW_7B", grounds: "NEW_EVIDENCE", text: "New vouchers", status: "PENDING" },
    }],
  })];
  show(<EmployerProceedingsPage />);

  expect(await screen.findByText("Applications")).toBeTruthy();
  expect(screen.queryByRole("form", { name: /Apply for a review/ })).toBeNull();

  cleanup();
  responses["/api/v1/employers/me/proceedings"] = [baseProceeding({
    applications: [{
      kind: "APPLICATION",
      at: "2026-10-03T10:00:00Z",
      detail: { application_id: "APP-01", kind: "REVIEW_7B", grounds: "NEW_EVIDENCE", text: "New vouchers", status: "REJECTED" },
    }],
  })];
  show(<EmployerProceedingsPage />);

  expect(await screen.findByRole("form", { name: /Apply for a review/ })).toBeTruthy();
});

it("shows applications list with kind, date, grounds label and status pill", async () => {
  as("employer.owner");
  responses["/api/v1/employers/me/proceedings"] = [baseProceeding({
    applications: [
      { kind: "APPLICATION", at: "2026-10-03T10:00:00Z", detail: { application_id: "APP-1", kind: "REVIEW_7B", grounds: "NEW_EVIDENCE", text: "Evidence", status: "PENDING" } },
      { kind: "APPLICATION", at: "2026-10-04T10:00:00Z", detail: { application_id: "APP-2", kind: "SET_ASIDE", grounds: "NOT_SERVED", text: "Notice", status: "GRANTED" } },
      { kind: "APPLICATION", at: "2026-10-05T10:00:00Z", detail: { application_id: "APP-3", kind: "REVIEW_7B", grounds: "OTHER_SUFFICIENT", text: "Other", status: "REJECTED" } },
      { kind: "APPLICATION", at: "2026-10-06T10:00:00Z", detail: { application_id: "APP-4", kind: "SET_ASIDE", grounds: "SUFFICIENT_CAUSE", text: "Cause", status: "SET_ASIDE" } },
    ],
  })];
  show(<EmployerProceedingsPage />);

  expect(await screen.findByText("Applications")).toBeTruthy();
  expect(screen.getAllByText(/Review under 7B/).length).toBe(2);
  expect(screen.getAllByText(/Set aside under 7A\(4\)/).length).toBe(2);
  expect(screen.getByText(/New and important evidence not available earlier despite due diligence/)).toBeTruthy();
  expect(screen.getByText(/The notice was not duly served/)).toBeTruthy();
  expect(screen.getByText(/Another sufficient reason/)).toBeTruthy();
  expect(screen.getByText(/A sufficient cause prevented appearance/)).toBeTruthy();

  expect(screen.getByText("Pending").className).toContain("state-pill");
  expect(screen.getByText("Granted").className).toContain("state-pill");
  expect(screen.getByText("Rejected").className).toContain("state-pill");
  expect(screen.getByText("Set aside").className).toContain("state-pill");
});

it("shows earlier order replaced on review when p.orders has more than one entry", async () => {
  as("employer.owner");
  responses["/api/v1/employers/me/proceedings"] = [baseProceeding({
    order: { kind: "ORDER", at: "2026-10-10T10:00:00Z", detail: { total_paise: 3420000, ex_parte: false, demand_id: "D7A-CMP-1-R1", text: "REVISED ORDER" } },
    orders: [
      { kind: "ORDER", at: "2026-10-02T10:00:00Z", detail: { total_paise: 5000000, ex_parte: true, demand_id: "D7A-CMP-1", text: "FIRST ORDER", superseded: true } },
      { kind: "ORDER", at: "2026-10-10T10:00:00Z", detail: { total_paise: 3420000, ex_parte: false, demand_id: "D7A-CMP-1-R1", text: "REVISED ORDER", superseded: false } },
    ],
  })];
  show(<EmployerProceedingsPage />);

  expect(await screen.findByText(/Earlier order replaced on review/)).toBeTruthy();
  expect(screen.getByText("₹50,000.00")).toBeTruthy();
  expect(screen.getByText("₹34,200.00")).toBeTruthy();
});
