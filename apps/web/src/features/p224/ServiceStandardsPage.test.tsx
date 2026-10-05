import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import i18n from "../../i18n";
import { ServiceStandardsPage } from "./ServiceStandardsPage";

vi.mock("../../api/client", () => ({ api: vi.fn() }));

beforeEach(() => {
  void i18n.changeLanguage("en");
  vi.mocked(api).mockResolvedValue({ data: {
    as_of: "2026-09-30", period_days: 30,
    standards: [{ code: "CLAIM_SETTLEMENT", name: "Claim settlement", days: 20, basis: "STATUTORY", availability: "NO_DATA", performance: null }],
    offices: [{ office_id: "RO-1", standards: [{ code: "CLAIM_SETTLEMENT", name: "Claim settlement", days: 20,
      basis: "STATUTORY", availability: "AVAILABLE", performance: { completed: 10, within_pct: 90,
        median_days: 5, p90_days: 12, open_past_standard: 1, met: false } }] }],
  }, meta: {} });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("shows published target, actual result and changes reporting period", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ServiceStandardsPage /></QueryClientProvider>);
  expect(await screen.findByText(/90% within standard/)).toBeTruthy();
  expect(screen.getByText("Not met")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Reporting period"), { target: { value: "90" } });
  await waitFor(() => expect(api).toHaveBeenCalledWith("/api/v1/public/service-standards?days=90"));
  client.clear();
});

it("has complete Hindi copy for the public result", async () => {
  await i18n.changeLanguage("hi");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ServiceStandardsPage /></QueryClientProvider>);
  expect(await screen.findByText(/90% मानक के भीतर/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "नागरिक अधिकार पत्र" })).toBeTruthy();
  expect(screen.getByText("पूरा नहीं हुआ")).toBeTruthy();
  client.clear();
});
