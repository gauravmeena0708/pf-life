import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, command } from "../../api/client";
import type { Envelope } from "../../api/client";
import { IndependentReviewMemberPage } from "./IndependentReviewMemberPage";

vi.mock("../../api/client", () => ({ api: vi.fn(), command: vi.fn() }));

describe("member independent review page", () => {
  beforeEach(() => {
    vi.mocked(api).mockResolvedValue({ data: { grievance_id: "GRV-1", state: "NOT_REQUESTED", request_deadline: "2026-10-20T00:00:00Z" }, meta: { correlation_id: "test", as_of: "2026-10-01T00:00:00Z" } } satisfies Envelope<{ grievance_id: string; state: string; request_deadline: string }>);
    vi.mocked(command).mockResolvedValue({});
  });
  it("shows the closure deadline and sends the member's reasons", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={["/member/grievances/GRV-1/review"]}><Routes><Route path="/member/grievances/:grievanceId/review" element={<IndependentReviewMemberPage />} /></Routes></MemoryRouter></QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText("Why you disagree with the resolution"), { target: { value: "The bank statement shows no payment." } });
    fireEvent.click(screen.getByRole("button", { name: "Request independent review" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/members/me/grievances/GRV-1/reviews", { reason: "The bank statement shows no payment." }));
  });
});
