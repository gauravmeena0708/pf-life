import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command } from "../../api/client";
import { AttachmentOrdersPage, type AttachmentOrder } from "./AttachmentOrders";

// The approver's confirmation: the step-up dialog is answered with a token.
vi.mock("../stepup/useStepUp", () => ({
  useStepUp: () => ({ ask: vi.fn().mockResolvedValue("step-token"), request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }),
}));
vi.mock("../../api/client", async (original) => ({
  ...await original<typeof import("../../api/client")>(),
  api: vi.fn(),
  command: vi.fn(),
}));

afterEach(cleanup);

function show(page: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>
  );
}

const mockOrders: AttachmentOrder[] = [
  {
    order_id: "ATT-ORD-0001",
    order_number: "EXEC-2026-99",
    court_name: "City Civil Court, Delhi",
    order_date: "2026-09-15",
    order_type: "COURT_DECREE",
    amount_paise: 15000000,
    target_uan: "100000000001",
    claim_id: "CLM-0001",
    debtor_name: "RAHUL SHARMA",
    status: "REFUSED",
    refusal_reason: "Refused under Section 10 of EPF Act: immune from attachment.",
    section: "EPF Act s.10",
    payments_diverted: false,
    created_at: "2026-09-15T10:00:00Z",
  },
  {
    order_id: "ATT-ORD-0002",
    order_number: "EPFO-RC-2026-01",
    court_name: "Recovery Officer, Delhi",
    order_date: "2026-09-20",
    order_type: "EPF_ACT_RECOVERY",
    amount_paise: 5000000,
    target_uan: "100000000002",
    claim_id: null,
    debtor_name: "PRIYA VERMA",
    status: "ACCEPTED",
    refusal_reason: null,
    section: "EPF Act s.10",
    payments_diverted: false,
    created_at: "2026-09-20T11:00:00Z",
  },
];

describe("AttachmentOrdersPage (P2.19)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders statutory s.10 banner and recorded orders table", async () => {
    vi.mocked(api).mockResolvedValue({ data: mockOrders, meta: {} });
    show(<AttachmentOrdersPage />);

    expect(await screen.findByText(/Statutory Immunity/i)).toBeTruthy();
    expect(screen.getByText(/immune from attachment under any decree or order of any court/i)).toBeTruthy();

    expect(await screen.findByText("ATT-ORD-0001")).toBeTruthy();
    expect(screen.getByText("EXEC-2026-99")).toBeTruthy();
    expect(screen.getByText("ATT-ORD-0002")).toBeTruthy();
    expect(screen.getByText("EPFO-RC-2026-01")).toBeTruthy();
    expect(screen.getByText("Protected under s.10 (Payments not diverted)")).toBeTruthy();
  });

  it("records a court decree attachment order and displays refusal citing EPF Act s.10", async () => {
    vi.mocked(api).mockResolvedValue({ data: [], meta: {} });
    vi.mocked(command).mockResolvedValue({
      data: {
        order_id: "ATT-ORD-9999",
        order_number: "COMM-SUIT-45",
        court_name: "High Court of Delhi",
        order_date: "2026-10-01",
        order_type: "COURT_DECREE",
        amount_paise: 20000000,
        target_uan: "100000000001",
        claim_id: null,
        debtor_name: "RAHUL SHARMA",
        status: "REFUSED",
        refusal_reason: "Refused under Section 10 of the EPF Act, 1952: accumulations immune from court decree.",
        section: "EPF Act s.10",
        payments_diverted: false,
        created_at: "2026-10-01T12:00:00Z",
      },
      meta: {},
    });

    show(<AttachmentOrdersPage />);

    const form = await screen.findByRole("form", { name: "Record received attachment order" });
    fireEvent.change(within(form).getByLabelText(/Order number/i), { target: { value: "COMM-SUIT-45" } });
    fireEvent.change(within(form).getByLabelText(/Court \/ Issuing/i), { target: { value: "High Court of Delhi" } });
    fireEvent.change(within(form).getByLabelText(/Date of order/i), { target: { value: "2026-10-01" } });
    fireEvent.change(within(form).getByLabelText(/Order category/i), { target: { value: "COURT_DECREE" } });
    fireEvent.change(within(form).getByLabelText(/Attachment amount/i), { target: { value: "200000" } });
    fireEvent.change(within(form).getByLabelText(/Target Member UAN/i), { target: { value: "100000000001" } });

    fireEvent.click(within(form).getByRole("button", { name: /Record order/i }));

    await waitFor(() => {
      expect(command).toHaveBeenCalledWith(
        "POST",
        "/api/v1/office/attachment-orders",
        expect.objectContaining({
          order_number: "COMM-SUIT-45",
          court_name: "High Court of Delhi",
          order_type: "COURT_DECREE",
          amount_paise: 20000000,
          target_uan: "100000000001",
        })
      );
    });

    expect(await screen.findByText(/Refusal Notice Generated \(EPF Act s\.10\)/i)).toBeTruthy();
    expect(screen.getByText(/Payments remain protected for member\/beneficiary/i)).toBeTruthy();
  });

  it("submits clear-hold for a shared bank account fraud held claim", async () => {
    vi.mocked(api).mockResolvedValue({ data: [], meta: {} });
    vi.mocked(command).mockResolvedValue({ data: { claim_id: "CLM-M1", state: "AUTO_APPROVED" }, meta: {} });

    show(<AttachmentOrdersPage />);

    const holdForm = await screen.findByRole("form", { name: "Clear shared bank account hold" });
    fireEvent.change(within(holdForm).getByLabelText(/Held claim ID/i), { target: { value: "CLM-M1" } });
    fireEvent.change(within(holdForm).getByLabelText(/Officer verification note/i), {
      target: { value: "Verified genuine identity documentation and bank account passbook" },
    });

    fireEvent.click(within(holdForm).getByRole("button", { name: /Verify & clear hold/i }));

    await waitFor(() => {
      expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/claims/CLM-M1/hold-releases", {
        note: "Verified genuine identity documentation and bank account passbook",
      }, { stepUpToken: "step-token" });
    });

    expect(await screen.findByText(/Claim CLM-M1: Hold cleared\. Proceeded to settlement processing\./i)).toBeTruthy();
  });
});
