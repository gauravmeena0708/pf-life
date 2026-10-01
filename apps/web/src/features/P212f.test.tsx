import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { api, command } from "../api/client";
import { homeFor, menusFor } from "../data/navigation";
import "../i18n";
import { ClaimantPage } from "./claimant/DeathClaimPages";
import { TotalisationClaims } from "./international/TotalisationClaims";
import { DrPage } from "./ndc/DrPage";
import { CampPage } from "./office/CampPage";
import { SandboxPage } from "./training/SandboxPage";

const { ask } = vi.hoisted(() => ({ ask: vi.fn() }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn() }));
vi.mock("./stepup/useStepUp", () => ({ useStepUp: () => ({ ask, request: null, onConfirmed: vi.fn(), onCancel: vi.fn() }) }));
vi.mock("./stepup/StepUpDialog", () => ({ StepUpDialog: () => null }));
let client: QueryClient;
const replication = { databases: [{ database: "claim", lag_seconds: 900, status: "LAGGING", last_applied_at: "2026-10-01T09:00:00Z" },
  { database: "member", lag_seconds: 2, status: "IN_SYNC", last_applied_at: "2026-10-01T09:15:00Z" }], overall_status: "LAGGING", rpo_minutes: 5 };
const agreements = { agreements: [{ country: "Germany", code: "DE", totalisation: true }, { country: "France", code: "FR", totalisation: false }], note: "Synthetic catalogue" };
function page(element: ReactElement) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks(); ask.mockResolvedValue("step-up-token");
  vi.mocked(api).mockImplementation(async (path) => ({ data: path.endsWith("replication-status") ? replication : path.endsWith("agreements") ? agreements : [], meta: {} }));
  vi.mocked(command).mockImplementation(async (_method, path) => ({ data: path.endsWith("failover-drills")
    ? { drill_id: "FDR-1", scenario: "DATABASE", steps: [{ step: "promote replica", duration_minutes: 9 }], rto_minutes: 21, target_minutes: 30, within_target: true, note: "Illustrative simulation only." }
    : path.endsWith("sandboxes") ? { sandbox_id: "SBX-1", expires_on: "2026-10-08", training_logins: [{ username: "trainee-1", persona: "member-a" }], note: "Synthetic data only." }
    : path.endsWith("assisted-requests") ? { reference: "NAN/NAN-RO1-2026-10/1", next_step: "The member submits the KYC update online.", camp: { camp_id: "NAN-RO1-2026-10", venue: "Office hall", request_counts: { KYC_UPDATE: 1 } } }
    : path.endsWith("totalisation-claims") ? { reference: "TOT/DE/1", liaison_office: "IWU, Head Office", months_by_country: { India: 12, Germany: 8 } }
    : { composite_ref: "CCF-1", next_step: "File Form 10D at the PRO counter.", claims: [{ claim_id: "CLM-PF", form_type: "FORM_20", state: "SUBMITTED" }, { claim_id: "CLM-EDLI", form_type: "FORM_5IF", state: "SUBMITTED" }] }, meta: {} }));
});
afterEach(() => { cleanup(); client?.clear(); });

test("DR shows lagging rows and records a simulated drill after step-up", async () => {
  page(<DrPage />);
  const row = await screen.findByRole("row", { name: /claim/ });
  expect(within(row).getByText("Lagging").className).toContain("dr-lagging");
  expect(screen.getByText(/Simulated — nothing is failed over/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "DATABASE" } });
  fireEvent.click(screen.getByRole("button", { name: "Run simulated drill" }));
  await waitFor(() => expect(ask).toHaveBeenCalledWith(expect.objectContaining({ action: "run-failover-drill", resourceId: "DATABASE" })));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/ndc/dr/failover-drills", { scenario: "DATABASE", notes: null }, { stepUpToken: "step-up-token" }));
  expect(await screen.findByText(/RTO 21 minutes/)).toBeTruthy(); expect(screen.getByText(/promote replica/)).toBeTruthy();
});

test("sandbox posts typed course, trainees, personas and date", async () => {
  page(<SandboxPage />); fireEvent.change(screen.getByLabelText("Course"), { target: { value: "Claims training" } });
  fireEvent.change(screen.getByLabelText("Trainees"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Starts on"), { target: { value: "2026-10-03" } });
  fireEvent.click(screen.getByLabelText("member-a")); fireEvent.click(screen.getByLabelText("ro-ao"));
  fireEvent.click(screen.getByRole("button", { name: "Create sandbox" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/training/sandboxes",
    { course: "Claims training", trainees: 2, personas: ["member-a", "ro-ao"], starts_on: "2026-10-03" }));
  expect(await screen.findByText(/Sandbox SBX-1/)).toBeTruthy(); expect(screen.getByText("trainee-1")).toBeTruthy();
});

test("camp request posts visitor details and shows next step and counts", async () => {
  page(<CampPage />); fireEvent.change(screen.getByLabelText("Request kind"), { target: { value: "KYC_UPDATE" } });
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Asha Devi" } });
  fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "9876543210" } });
  fireEvent.change(screen.getByLabelText("Details"), { target: { value: "Needs KYC assistance" } });
  fireEvent.click(screen.getByRole("button", { name: "Record request" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/outreach-camps/NAN-RO1-2026-10/assisted-requests",
    { kind: "KYC_UPDATE", name: "Asha Devi", mobile: "9876543210", uan: null, details: "Needs KYC assistance" }));
  expect(await screen.findByText(/The member submits the KYC update online/)).toBeTruthy(); expect(screen.getByText("KYC update: 1")).toBeTruthy();
});

test("totalisation posts two coverage periods under an eligible agreement", async () => {
  page(<TotalisationClaims />); await waitFor(() => expect(within(screen.getByLabelText("Agreement country")).getByRole("option", { name: "Germany" })).toBeTruthy());
  expect(within(screen.getByLabelText("Agreement country")).queryByRole("option", { name: "France" })).toBeNull();
  fireEvent.change(screen.getByLabelText("UAN"), { target: { value: "100000000001" } });
  fireEvent.change(screen.getByLabelText("Foreign insurance number"), { target: { value: "DE-123" } });
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2020-01-01" } });
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "2020-12-31" } });
  fireEvent.click(screen.getByRole("button", { name: "Add period" }));
  fireEvent.change(screen.getAllByLabelText("From")[1], { target: { value: "2021-01-01" } });
  fireEvent.change(screen.getAllByLabelText("To")[1], { target: { value: "2021-08-31" } });
  fireEvent.click(screen.getByRole("button", { name: "Route totalisation claim" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/international/totalisation-claims", expect.objectContaining({
    country: "Germany", uan: "100000000001", foreign_insurance_no: "DE-123", periods: [
      { from: "2020-01-01", to: "2020-12-31", country: "India" }, { from: "2021-01-01", to: "2021-08-31", country: "Germany" }],
  })));
  expect(await screen.findByText(/TOT\/DE\/1/)).toBeTruthy(); expect(screen.getByText("Germany: 8 months")).toBeTruthy();
});

test("composite death filing shows the reference and both claims", async () => {
  page(<ClaimantPage />); fireEvent.change(screen.getByLabelText("Claim", { exact: true }), { target: { value: "CCF_DEATH" } });
  fireEvent.click(screen.getByRole("button", { name: "File claim" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/claimants/death-claims",
    { form_type: "CCF_DEATH", deceased_uan: "100000000901", process_as: "E_NOMINATION" }, { stepUpToken: "step-up-token" }));
  expect(await screen.findByText(/Composite reference CCF-1/)).toBeTruthy(); expect(screen.getByText(/CLM-PF/)).toBeTruthy(); expect(screen.getByText(/CLM-EDLI/)).toBeTruthy();
});

test.each([["tech.adc", "/ndc/dr"], ["train.pdnasa", "/training"], ["train.zti", "/training"], ["zo.zti", "/training"], ["fo.nan", "/office/nan-camp"]])("%s opens its page", (role, path) => {
  expect(homeFor(role)).toBe(path); expect(menusFor(role)).toContainEqual(expect.objectContaining({ to: path }));
});
