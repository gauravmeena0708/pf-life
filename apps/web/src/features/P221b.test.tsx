import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command } from "../api/client";
import "../i18n";
import { ClaimantPage } from "./claimant/DeathClaimPages";
import { DigiLockerSection } from "./member/KycPage";
import { RegistryDeathsPage } from "./office/RegistryDeathsPage";
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn() }));
afterEach(cleanup);

const wrap = (node: ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
  <MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);

it("offers the nominee the claims on a recorded death, worked out (P2.21b)", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/claimants/me/death-claim-offers") return { data: [{ deceased_uan: "100000000916", deceased_name: "VIJAY DEMO",
      date_of_death: "2026-09-30", relation: "SPOUSE", share_pct: 100, open: ["FORM_20", "FORM_5IF"], family_pension: "The spouse may also apply.",
      forms: [{ form_type: "FORM_20", label: "Provident Fund (Form 20)", amount_paise: 15000000, working: "The PF balance", filed_claim_id: null },
        { form_type: "FORM_5IF", label: "EDLI insurance (Form 5IF)", amount_paise: 25000000, working: "35 x wages", filed_claim_id: null }] }], meta: {} };
    throw new Error("not available");
  });
  wrap(<ClaimantPage />);
  expect(await screen.findByRole("heading", { name: "What you can claim" })).toBeTruthy();
  expect(screen.getByText(/VIJAY DEMO · died 2026-09-30/)).toBeTruthy();
  expect(screen.getByText(/₹1,50,000/)).toBeTruthy();
  expect((await screen.findAllByDisplayValue("100000000916")).length).toBe(2);          // the claim and Form 10D forms, filled in
  const original = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value(this: HTMLDialogElement) { this.open = true; } });
  vi.mocked(command).mockResolvedValue({ data: { challenge_id: "STEP-1", demo_otp: "123456", demo_notice: "Mock code." }, meta: {} });
  try {
    fireEvent.click(screen.getByRole("button", { name: "File PF and EDLI together" }));
    await screen.findByText("Mock code.");                                         // the step-up asks before anything is filed
    expect(command).toHaveBeenCalledWith("POST", "/api/v1/security/step-up-challenges", expect.objectContaining({
      action: "file-death-claim", resource_id: "100000000916", summary: "File the composite PF and EDLI claim for the member with UAN ending 0916." }));
  } finally {
    if (original) Object.defineProperty(HTMLDialogElement.prototype, "showModal", original);
  }
});

it("lists documents in DigiLocker and offers the e-UAN card when none was issued (P2.21b)", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/members/me/digilocker-documents") return { data: [{ doc_id: "DL-1", doc_type: "PPO", title: "e-PPO — PPO-DEMO-0003",
      state: "ISSUED", uri: "in.gov.epfindia.demo-PPO-ABC", attempts: 1, last_error: null, issued_at: "2026-10-04T10:00:00+00:00" }], meta: {} };
    throw new Error("not available");
  });
  wrap(<DigiLockerSection />);
  expect(await screen.findByText("e-PPO — PPO-DEMO-0003")).toBeTruthy();
  expect(screen.getByText(/in.gov.epfindia.demo-PPO-ABC, issued 2026-10-04/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Send my e-UAN card to DigiLocker" })).toBeTruthy();
});

it("shows the office what the civil registry reported, matched or not (P2.21b)", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/api/v1/office/civil-registry/deaths") return { data: [
      { registration_no: "D-1", name: "VIJAY DEMO", date_of_death: "2026-09-30", matched_uan: "100000000916", matched_by: "AADHAAR", outcome: "RECORDED", exits_marked: ["AL-0960"], received_at: "2026-10-01T09:00:00+00:00" },
      { registration_no: "D-2", name: "ESHA DEMO", date_of_death: "2026-09-01", matched_uan: null, matched_by: null, outcome: "AMBIGUOUS", exits_marked: [], received_at: "2026-10-01T09:00:00+00:00" }], meta: {} };
    throw new Error("not available");
  });
  wrap(<RegistryDeathsPage />);
  expect(await screen.findByText(/by Aadhaar; exit marked on AL-0960/)).toBeTruthy();
  expect(screen.getByText(/Matched more than one person/)).toBeTruthy();
});
