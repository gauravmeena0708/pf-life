import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, command } from "../../api/client";
import type { Envelope } from "../../api/client";
import { IndependentReviewQueuePage } from "./IndependentReviewQueuePage";

vi.mock("../../api/client", () => ({ api: vi.fn(), command: vi.fn() }));

const response: Envelope<Array<{ grievance_id: string; state: string; original_resolution: string; reason: string; request_deadline: string; decision_due_at: string; subject: string; office_id: string }>> = {
  data: [{ grievance_id: "GRV-1", state: "PENDING", original_resolution: "Payment was sent.", reason: "The payment is missing.", request_deadline: "2026-10-20T00:00:00Z", decision_due_at: "2026-11-01T00:00:00Z", subject: "Payment delay", office_id: "RO-1" }],
  meta: { correlation_id: "test", as_of: "2026-10-01T00:00:00Z" },
};

describe("independent review queue", () => {
  beforeEach(() => { vi.mocked(api).mockResolvedValue(response); vi.mocked(command).mockResolvedValue({}); });
  it("shows deadlines and submits a reasoned fresh-decision outcome", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><IndependentReviewQueuePage /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText("RO-1")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Review outcome"), { target: { value: "FRESH_DECISION" } });
    fireEvent.change(screen.getByLabelText("Reasons"), { target: { value: "The evidence supports a new decision." } });
    fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/grievance-reviews/GRV-1/decisions", {
      outcome: "FRESH_DECISION", reasons: "The evidence supports a new decision.",
    }));
  });
});
