import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { api, command, getSession } from "../api/client";
import { menusFor } from "../data/navigation";
import "../i18n";
import { MessagePreferences } from "./member/MessagePreferences";
import { ProfilePage } from "./member/ProfilePage";
import { DeliveriesPage } from "./office/DeliveriesPage";

vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), api: vi.fn(), command: vi.fn(), getSession: vi.fn() }));
vi.mock("./member/CorrectionForm", () => ({ CorrectionForm: () => null }));
vi.mock("./member/PensionEstimate", () => ({ PensionEstimate: () => null }));
let responses: Record<string, unknown>;
beforeEach(() => { vi.clearAllMocks(); responses = {}; vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "fo.pro" }); vi.mocked(api).mockImplementation(async (path) => { if (!(path in responses)) throw new Error(`No mock response: ${path}`); return { data: responses[path], meta: {} }; }); vi.mocked(command).mockResolvedValue({ data: {}, meta: {} }); });
afterEach(cleanup);
function show(page: ReactElement) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>); }
const now = "2026-10-02T09:00:00+00:00";
const failed = { delivery_id: "D-1", recipient_subject: "member-1", channel: "EMAIL", destination_masked: "a***@bounce.invalid", template: "CLAIM_SUBMITTED", state: "FAILED", attempts: 1, reason: "BOUNCED", updated_at: now, attempts_evidence: [{ attempt: 1, at: now, outcome: "FAILED", http_status: 502, gateway_message_id: "gw-1", error: "BOUNCED" }] };

it("shows each channel's masked delivery state below a member notice", async () => {
  responses["/api/v1/members/me/notifications"] = [{ id: "N-1", template: "CLAIM_SUBMITTED", reference_id: "C-1", title: "Claim submitted", body: "Your claim was submitted.", created_at: now, read_at: null, deliveries: [
    { channel: "SMS", state: "DELIVERED", attempts: 1, destination_masked: "******0914", updated_at: now, reason: null },
    { channel: "EMAIL", state: "FAILED", attempts: 1, destination_masked: "a***@bounce.invalid", updated_at: now, reason: "BOUNCED" }] },
    { id: "N-2", template: "CLAIM_SUBMITTED", reference_id: "C-2", title: "Another claim", body: "Another notice.", created_at: now, read_at: null, deliveries: [
      { channel: "EMAIL", state: "SKIPPED", attempts: 0, destination_masked: "a***@bounce.invalid", updated_at: now, reason: "Member turned EMAIL off" }] }];
  show(<ProfilePage />);
  expect(await screen.findByText("SMS to ******0914 · Delivered")).toBeTruthy();
  expect(screen.getByText("E-mail to a***@bounce.invalid · Failed: BOUNCED")).toBeTruthy();
  expect(screen.getByText("Skipped (you turned E-mail off)")).toBeTruthy();
});

it("saves SMS, e-mail and language preferences together", async () => {
  responses["/api/v1/members/me/notification-preferences"] = { sms: true, email: true, language: "en", essential_sms_titles: ["Contact details changed"], essential_sms_notice: "Essential messages still go by SMS." };
  vi.mocked(command).mockResolvedValue({ data: responses["/api/v1/members/me/notification-preferences"], meta: {} });
  show(<MessagePreferences />);
  expect(await screen.findByText("Contact details changed")).toBeTruthy();
  fireEvent.click(screen.getByRole("checkbox", { name: "E-mail" }));
  fireEvent.change(screen.getByLabelText("Message language"), { target: { value: "hi" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(command).toHaveBeenCalledWith("PUT", "/api/v1/members/me/notification-preferences", { sms: true, email: false, language: "hi" }));
});

it.each(["fo.pro", "ho.is"])("shows gateway evidence to %s and limits retry", async (role) => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: role });
  responses["/api/v1/office/notification-deliveries?state=FAILED"] = [failed];
  show(<DeliveriesPage />);
  expect(await screen.findByText("a***@bounce.invalid")).toBeTruthy();
  expect(api).toHaveBeenCalledWith("/api/v1/office/notification-deliveries?state=FAILED");
  fireEvent.click(screen.getByRole("button", { name: "Attempts evidence" }));
  const evidence = screen.getByText("Gateway attempts").parentElement!;
  expect(within(evidence).getByText("502")).toBeTruthy();
  expect(within(evidence).getByText("gw-1")).toBeTruthy();
  if (role === "fo.pro") { fireEvent.click(screen.getByRole("button", { name: "Send again" })); await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/notification-deliveries/D-1/retries")); }
  else expect(screen.queryByRole("button", { name: "Send again" })).toBeNull();
});

it("hides retry on a non-failed row and links the right menus", async () => {
  responses["/api/v1/office/notification-deliveries?state=FAILED"] = [{ ...failed, state: "DELIVERED" }];
  show(<DeliveriesPage />);
  expect(await screen.findByText("a***@bounce.invalid")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Send again" })).toBeNull();
  expect(menusFor("member").find((group) => group.label === "Account")?.items).toContainEqual({ labelKey: "messages.heading", to: "/member/security#messages-heading" });
  expect(menusFor("fo.pro").find((group) => group.label === "Office")?.items).toContainEqual({ label: "SMS / e-mail deliveries", to: "/office/notification-deliveries" });
  expect(menusFor("ho.is")).toContainEqual({ label: "SMS / e-mail gateway", to: "/office/notification-deliveries" });
});
