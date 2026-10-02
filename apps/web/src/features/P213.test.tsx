import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { api, command } from "../api/client";
import "../i18n";
import { PensionApplicationPage } from "./member/PensionApplicationPage";
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask: vi.fn(), request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
afterEach(cleanup);

it("files a disablement pension with the medical certificate (EPS para 15)", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/members/me/pension-applications") return { data: [], meta: {} };
    if (path === "/api/v1/members/me") return { data: { uan: "100000000915" }, meta: {} };
    throw new Error("not found");
  });
  vi.mocked(command).mockResolvedValue({ data: { claim_id: "PC-1", pension_from: "2026-08-21", estimate: { monthly_paise: 150000 } }, meta: {} });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><PensionApplicationPage /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(await screen.findByText(/Apply for a disablement pension/));
  const form = screen.getByRole("form", { name: "Disablement pension" });
  fireEvent.change(within(form).getByLabelText("Date of disablement"), { target: { value: "2026-08-12" } });
  fireEvent.change(within(form).getByLabelText("Certificate number"), { target: { value: "MB/DL/2026/0815" } });
  fireEvent.change(within(form).getByLabelText("Issued by"), { target: { value: "Medical Board" } });
  fireEvent.click(within(form).getByLabelText(/permanently and totally unfit/));
  fireEvent.click(within(form).getByRole("button", { name: "Apply for disablement pension" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/members/me/pension-applications", { disablement: {
    date_of_disablement: "2026-08-12", certificate_kind: "MEDICAL_BOARD", certificate_ref: "MB/DL/2026/0815", issued_by: "Medical Board", permanent_and_total: true } }));
  expect(await screen.findByText(/disablement pension \(PC-1\); pension from 2026-08-21/)).toBeTruthy();
});

it("lets the zone grant or refuse instalments referred by a region (P2.13b)", async () => {
  const { InstalmentReferralsPage } = await import("./office/InstalmentReferralsPage");
  const { menusFor } = await import("../data/navigation");
  vi.mocked(api).mockResolvedValue({ data: [{ recovery_case_id: "RC-1", certificate_no: "RC/RO-DEMO-01/2026/1234", establishment_id: "EST-DEMO-0002",
    legal_name: "Demo Engineering Works", office_id: "RO-DEMO-01", outstanding_paise: 3000000, count: 12, note: "Above the region's power", by_rank: "RPFC-I",
    referred_at: "2026-10-02T10:00:00+00:00" }], meta: {} });
  vi.mocked(command).mockResolvedValue({ data: {}, meta: {} });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><InstalmentReferralsPage /></MemoryRouter></QueryClientProvider>);
  const grant = await screen.findByRole("form", { name: "Grant RC-1" });
  fireEvent.change(within(grant).getByLabelText("First due"), { target: { value: "2026-11-01" } });
  fireEvent.change(within(grant).getByLabelText("Bank guarantee (₹)"), { target: { value: "2500" } });
  fireEvent.change(within(grant).getByLabelText("Guarantee reference"), { target: { value: "BG-1" } });
  fireEvent.change(within(grant).getByLabelText("Note"), { target: { value: "Hardship shown" } });
  fireEvent.click(within(grant).getByRole("button", { name: "Grant instalments" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/recovery/RC-1/instalments",
    { count: 12, first_due: "2026-11-01", note: "Hardship shown", bank_guarantee_paise: 250000, bank_guarantee_ref: "BG-1" }));
  const refuse = screen.getByRole("form", { name: "Refuse RC-1" });
  fireEvent.change(within(refuse).getByLabelText("Reasons"), { target: { value: "No hardship shown in the papers" } });
  fireEvent.click(within(refuse).getByRole("button", { name: "Refuse" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/zo/recovery/instalment-referrals/RC-1/refusals", { reasons: "No hardship shown in the papers" }));
  expect(menusFor("zo.acc").some((g) => g.to === "/zo/instalments")).toBe(true);
  expect(menusFor("ho.cpfc").some((g) => g.to === "/zo/instalments")).toBe(true);
});
