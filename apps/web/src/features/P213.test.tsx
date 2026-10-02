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
