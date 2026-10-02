import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import "../i18n";
import { LegalPage, type LegalCase } from "./office/LegalPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: vi.fn(),
  command: vi.fn(),
  getSession: vi.fn(),
  newIdempotencyKey: () => "key-1",
}));

vi.mock("./stepup/useStepUp", () => ({
  useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }),
}));

vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));

let responses: Record<string, unknown>;
const as = (stakeholder: string) =>
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder });

beforeEach(() => {
  vi.clearAllMocks();
  ask.mockResolvedValue("step-token");
  responses = { "/api/v1/office/legal/cases": [] };
  vi.mocked(api).mockImplementation(async (path) => ({
    data: responses[path] ?? responses[path.split("?")[0]],
    meta: {},
  }));
  vi.mocked(command).mockResolvedValue({ data: {}, meta: {} });
});

afterEach(cleanup);

function show(page: ReactElement) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>
  );
}

const sampleAppeal: LegalCase = {
  legal_case_id: "LC-101",
  establishment_id: "EST-DEMO-0001",
  kind: "APPEAL_7I",
  forum: "CGIT-cum-Labour Court (EPF Appellate Tribunal)",
  case_no: "ATA-45/2026",
  filed_on: "2026-10-01",
  inquiry_case_id: "CMP-DEMO-001",
  amount_paise: 10000000,
  pre_deposit_percent: 75,
  pre_deposit_required_paise: 7500000,
  pre_deposited_paise: 0,
  pre_deposits: [],
  delay_condonation: false,
  stayed: false,
  state: "PENDING",
  orders: [],
  note: "Under appeal",
  heard: false,
};

it("submits the appeal registration body", async () => {
  as("fo.legal");
  responses["/api/v1/office/legal/cases"] = [];
  show(<LegalPage />);
  const form = await screen.findByRole("form", { name: "Register an appeal (section 7-I)" });
  fireEvent.change(within(form).getByLabelText(/Inquiry case ID/i), { target: { value: "CMP-DEMO-001" } });
  fireEvent.change(within(form).getByLabelText(/Tribunal case number/i), { target: { value: "ATA-45/2026" } });
  fireEvent.change(within(form).getByLabelText(/Filed on/i), { target: { value: "2026-10-01" } });
  fireEvent.click(within(form).getByLabelText(/Delay condonation/i));
  fireEvent.change(within(form).getByLabelText(/Note/i), { target: { value: "Appeal filed with delay condonation" } });
  fireEvent.click(within(form).getByRole("button", { name: "Register appeal" }));
  await waitFor(() =>
    expect(command).toHaveBeenCalledWith(
      "POST",
      "/api/v1/office/compliance/cases/CMP-DEMO-001/appeals",
      {
        forum: "CGIT-cum-Labour Court (EPF Appellate Tribunal)",
        case_no: "ATA-45/2026",
        filed_on: "2026-10-01",
        delay_condonation: true,
        note: "Appeal filed with delay condonation",
      }
    )
  );
});

it("submits the pre-deposit body with the idempotency key", async () => {
  as("fo.legal");
  responses["/api/v1/office/legal/cases"] = [sampleAppeal];
  show(<LegalPage />);
  const form = await screen.findByRole("form", { name: "Record a pre-deposit" });
  fireEvent.change(within(form).getByLabelText(/Amount/i), { target: { value: "25000" } });
  fireEvent.change(within(form).getByLabelText(/Reference/i), { target: { value: "TRRN-998877" } });
  fireEvent.change(within(form).getByLabelText(/Deposited on/i), { target: { value: "2026-10-02" } });
  fireEvent.click(within(form).getByRole("button", { name: "Record pre-deposit" }));
  await waitFor(() =>
    expect(command).toHaveBeenCalledWith(
      "POST",
      "/api/v1/office/compliance/cases/CMP-DEMO-001/appeals/LC-101/pre-deposits",
      {
        amount_paise: 2500000,
        reference: "TRRN-998877",
        deposited_on: "2026-10-02",
      },
      { idempotencyKey: "key-1" }
    )
  );
});

it("records a pre-deposit waiver using the one-time code", async () => {
  as("fo.legal");
  responses["/api/v1/office/legal/cases"] = [sampleAppeal];
  show(<LegalPage />);
  const form = await screen.findByRole("form", { name: "Record the Tribunal's reduction or waiver" });
  fireEvent.change(within(form).getByLabelText(/Percent/i), { target: { value: "25" } });
  fireEvent.change(within(form).getByLabelText(/Tribunal order ref/i), { target: { value: "CGIT-ORD-01" } });
  fireEvent.change(within(form).getByLabelText(/Order date/i), { target: { value: "2026-10-02" } });
  fireEvent.click(within(form).getByRole("button", { name: "Record waiver" }));
  await waitFor(() =>
    expect(ask).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "record-pre-deposit-waiver",
        resourceId: "LC-101",
      })
    )
  );
  await waitFor(() =>
    expect(command).toHaveBeenCalledWith(
      "POST",
      "/api/v1/office/compliance/cases/CMP-DEMO-001/appeals/LC-101/pre-deposit-waivers",
      {
        percent: 25,
        tribunal_order_ref: "CGIT-ORD-01",
        order_date: "2026-10-02",
      },
      { stepUpToken: "step-token" }
    )
  );
});

it("submits the record order body with revised amount in paise for PARTLY_ALLOWED and displays the effect", async () => {
  as("fo.legal");
  responses["/api/v1/office/legal/cases"] = [sampleAppeal];
  vi.mocked(command).mockResolvedValue({
    data: { ...sampleAppeal, effect: "demand revised" },
    meta: {},
  } as unknown as { data: LegalCase & { effect?: string }; meta: Record<string, unknown> });
  show(<LegalPage />);
  const form = await screen.findByRole("form", { name: "Record an order" });
  fireEvent.change(within(form).getByLabelText(/Order date/i), { target: { value: "2026-10-03" } });
  fireEvent.change(within(form).getByLabelText(/Outcome/i), { target: { value: "PARTLY_ALLOWED" } });
  fireEvent.change(within(form).getByLabelText(/Revised amount/i), { target: { value: "50000" } });
  fireEvent.change(within(form).getByLabelText(/Note/i), { target: { value: "Tribunal partially allowed appeal" } });
  fireEvent.click(within(form).getByRole("button", { name: "Record order" }));
  await waitFor(() =>
    expect(command).toHaveBeenCalledWith(
      "POST",
      "/api/v1/office/legal/cases/LC-101/orders",
      {
        order_date: "2026-10-03",
        outcome: "PARTLY_ALLOWED",
        revised_amount_paise: 5000000,
        note: "Tribunal partially allowed appeal",
      }
    )
  );
  expect(await screen.findByText(/demand revised/)).toBeTruthy();
});

it("offers prosecution outcomes only for prosecutions", async () => {
  as("fo.legal");
  const prosCase: LegalCase = {
    legal_case_id: "LC-PROS",
    establishment_id: "EST-DEMO-0001",
    kind: "PROSECUTION",
    forum: "CJM Court",
    case_no: "CC-101/2026",
    filed_on: "2026-09-01",
    inquiry_case_id: null,
    amount_paise: null,
    pre_deposit_percent: null,
    pre_deposits: null,
    delay_condonation: null,
    stayed: false,
    state: "PENDING",
    orders: [],
    note: "Criminal complaint",
  };
  const writCase: LegalCase = {
    legal_case_id: "LC-WRIT",
    establishment_id: "EST-DEMO-0001",
    kind: "WRIT",
    forum: "High Court of Delhi",
    case_no: "WP(C)-202/2026",
    filed_on: "2026-09-02",
    inquiry_case_id: null,
    amount_paise: null,
    pre_deposit_percent: null,
    pre_deposits: null,
    delay_condonation: null,
    stayed: false,
    state: "PENDING",
    orders: [],
    note: "Writ challenging notification",
  };
  responses["/api/v1/office/legal/cases"] = [prosCase, writCase];
  show(<LegalPage />);

  const prosCard = await screen.findByRole("article", { name: "Legal case CC-101/2026" });
  const prosForm = within(prosCard).getByRole("form", { name: "Record an order" });
  const prosSelect = within(prosForm).getByLabelText(/Outcome/i) as HTMLSelectElement;
  const prosOptions = Array.from(prosSelect.options).map((o) => o.value);
  expect(prosOptions).toEqual(expect.arrayContaining(["CONVICTED", "ACQUITTED", "OTHER", "INTERIM_STAY"]));
  expect(prosOptions).not.toContain("DISMISSED");
  expect(prosOptions).not.toContain("ALLOWED");
  expect(prosOptions).not.toContain("PARTLY_ALLOWED");
  expect(prosOptions).not.toContain("REMANDED");

  const writCard = screen.getByRole("article", { name: "Legal case WP(C)-202/2026" });
  const writForm = within(writCard).getByRole("form", { name: "Record an order" });
  const writSelect = within(writForm).getByLabelText(/Outcome/i) as HTMLSelectElement;
  const writOptions = Array.from(writSelect.options).map((o) => o.value);
  expect(writOptions).toEqual(
    expect.arrayContaining(["INTERIM_STAY", "STAY_VACATED", "DISMISSED", "ALLOWED", "PARTLY_ALLOWED", "REMANDED", "OTHER"])
  );
  expect(writOptions).not.toContain("CONVICTED");
  expect(writOptions).not.toContain("ACQUITTED");
});

it("shows the pre-deposit status and the Stayed pill on the register", async () => {
  as("fo.legal");
  const stayedAppeal: LegalCase = {
    legal_case_id: "LC-102",
    establishment_id: "EST-DEMO-0001",
    kind: "APPEAL_7I",
    forum: "CGIT-cum-Labour Court (EPF Appellate Tribunal)",
    case_no: "ATA-99/2026",
    filed_on: "2026-09-10",
    inquiry_case_id: "CMP-DEMO-002",
    amount_paise: 10000000,
    pre_deposit_percent: 75,
    pre_deposit_required_paise: 7500000,
    pre_deposited_paise: 2500000,
    pre_deposits: [{ amount_paise: 2500000, reference: "TRRN-887766", deposited_on: "2026-09-15" }],
    delay_condonation: true,
    stayed: true,
    state: "PENDING",
    orders: [{ order_date: "2026-09-20", outcome: "INTERIM_STAY", note: "Interim stay granted" }],
    note: "Impugning 7A order",
    heard: false,
  };
  responses["/api/v1/office/legal/cases"] = [stayedAppeal];
  show(<LegalPage />);

  expect(await screen.findByText("Stayed")).toBeTruthy();
  expect(screen.getByText(/₹25,000.*of.*₹75,000.*deposited \(75%\)/i)).toBeTruthy();
  expect(screen.getByText(/Cannot be heard/i)).toBeTruthy();
});

it("submits registration for another case", async () => {
  as("fo.legal");
  responses["/api/v1/office/legal/cases"] = [];
  show(<LegalPage />);
  const form = await screen.findByRole("form", { name: "Register another case" });
  fireEvent.change(within(form).getByLabelText(/Establishment ID/i), { target: { value: "EST-DEMO-0001" } });
  fireEvent.change(within(form).getByLabelText(/Kind/i), { target: { value: "WRIT" } });
  fireEvent.change(within(form).getByLabelText(/Forum/i), { target: { value: "High Court of Delhi" } });
  fireEvent.change(within(form).getByLabelText(/Case number/i), { target: { value: "WP(C) 555/2026" } });
  fireEvent.change(within(form).getByLabelText(/Filed on/i), { target: { value: "2026-10-01" } });
  fireEvent.change(within(form).getByLabelText(/Linked inquiry case/i), { target: { value: "CMP-DEMO-001" } });
  fireEvent.change(within(form).getByLabelText(/Note/i), { target: { value: "Challenging assessment" } });
  fireEvent.click(within(form).getByRole("button", { name: "Register case" }));
  await waitFor(() =>
    expect(command).toHaveBeenCalledWith(
      "POST",
      "/api/v1/office/legal/cases",
      {
        establishment_id: "EST-DEMO-0001",
        kind: "WRIT",
        forum: "High Court of Delhi",
        case_no: "WP(C) 555/2026",
        filed_on: "2026-10-01",
        inquiry_case_id: "CMP-DEMO-001",
        note: "Challenging assessment",
      }
    )
  );
});
