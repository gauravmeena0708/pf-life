import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api, command } from "../api/client";
import { menusFor } from "../data/navigation";
import "../i18n";
import { PastAccumulationReco } from "./office/PastAccumulationReco";
const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
const URL = "/api/v1/office/exempted/past-accumulation-vdr-reconciliations";
const position = (recos: unknown[] = []) => [{ establishment_id: "EST-DEMO-0003", legal_name: "Trust Demo Ltd", credited_paise: 470000, received_paise: 0,
  outstanding_paise: 470000, unreconciled_receipts: [{ vdr_id: "VDR-1", instrument: "DD", instrument_ref: "DD-778899", amount_paise: 300000, received_on: "2026-09-20" }],
  reconciliations: recos }];
beforeEach(() => { vi.clearAllMocks(); ask.mockResolvedValue("step-token"); vi.mocked(command).mockResolvedValue({ data: { reco_id: "PAR-1", receipts_paise: 400000,
  state: "SHORT", summary: { outstanding_after_paise: 70000, statement_difference_paise: 0 } }, meta: {} }); });
afterEach(cleanup);
const show = (role: string) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
  <MemoryRouter><PastAccumulationReco role={role} /></MemoryRouter></QueryClientProvider>);

it("lets DA (Accounts) propose the receipts of a trust's past accumulations", async () => {
  vi.mocked(api).mockResolvedValue({ data: position(), meta: {} });
  show("fo.da_accounts");
  const form = await screen.findByRole("form", { name: "Reconcile EST-DEMO-0003" });
  fireEvent.click(within(form).getByLabelText(/DD-778899/));
  fireEvent.change(within(form).getByLabelText("SDS — Investment Division reference"), { target: { value: "INV/SDS/2026/41" } });
  fireEvent.change(within(form).getByLabelText("SDS amount (₹)"), { target: { value: "1000" } });
  fireEvent.change(within(form).getByLabelText("Form SE-6 statement total (₹)"), { target: { value: "4700" } });
  fireEvent.click(within(form).getByRole("button", { name: "Propose the reconciliation" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/exempted/EST-DEMO-0003/past-accumulation-vdr-reconciliations", {
    statement_total_paise: 470000, note: "",
    receipts: [{ component: "CASH", vdr_id: "VDR-1" }, { component: "SDS", ho_reference: "INV/SDS/2026/41", amount_paise: 100000 }] }));
  expect(await screen.findByText(/₹700(\.00)? would remain outstanding/)).toBeTruthy();
});

it("lets the APFC approve with step-up, and links the menus", async () => {
  vi.mocked(api).mockResolvedValue({ data: position([{ reco_id: "PAR-1", statement_total_paise: 470000, receipts: [{ component: "CASH", reference: "DD DD-778899", amount_paise: 300000 }],
    receipts_paise: 400000, state: "PROPOSED", summary: { outstanding_after_paise: 70000, statement_difference_paise: 0 } }]), meta: {} });
  show("fo.apfc");
  fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "approve-pa-reco", resourceId: "PAR-1", amountPaise: 400000 })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", `${URL}/PAR-1/approvals`, expect.objectContaining({ decision: "APPROVE" }), { stepUpToken: "step-token" }));
  const item = (role: string, label: string) => menusFor(role).flatMap((g) => g.items ?? []).find((i) => i.label === label);
  expect(item("fo.apfc", "PAST ACCUM VDR RECO")?.to).toBe("/office/ledger#pa-reco-heading");
  expect(item("fo.exemption", "PAST ACCUM BULK TRANSFER")?.to).toBe("/office/exempted#past-accumulation-heading");
});
