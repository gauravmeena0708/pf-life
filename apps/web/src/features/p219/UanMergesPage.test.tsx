import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ApiError, api, command } from "../../api/client";
import { UanMergesPage } from "./UanMergesPage";

vi.mock("../../api/client", async (original) => ({
  ...await original<typeof import("../../api/client")>(),
  api: vi.fn(), command: vi.fn(),
}));
vi.mock("../stepup/StepUpDialog", () => ({
  StepUpDialog: ({ request, onConfirmed }: { request: { action: string; resourceId: string } | null; onConfirmed: (token: string) => void }) =>
    request ? <div role="dialog" aria-label="Confirm UAN merge">
      <span>{request.action}: {request.resourceId}</span>
      <button type="button" onClick={() => onConfirmed("confirmed-token")}>Confirm merge</button>
    </div> : null,
}));

const merge = {
  merge_id: "MERGE-123", active_uan: "100000000001", duplicate_uan: "100000000002",
  account_link_ids: ["AL-1", "AL-2"], note: "Verified identity", merged_by: "officer-1", merged_at: "2026-10-05T10:30:00Z",
};

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><UanMergesPage /></MemoryRouter></QueryClientProvider>);
}

function fill() {
  fireEvent.change(screen.getByLabelText("Active UAN"), { target: { value: merge.active_uan } });
  fireEvent.change(screen.getByLabelText("Duplicate UAN"), { target: { value: merge.duplicate_uan } });
  fireEvent.change(screen.getByLabelText("Officer note"), { target: { value: merge.note } });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api).mockResolvedValue({ data: [], meta: { correlation_id: "test", as_of: "2026-10-05" } });
});
afterEach(cleanup);

describe("UanMergesPage", () => {
  it("lists validation errors at the top as the UANs are typed", () => {
    show();
    fireEvent.change(screen.getByLabelText("Active UAN"), { target: { value: "123" } });
    fireEvent.change(screen.getByLabelText("Duplicate UAN"), { target: { value: "abc" } });
    const summary = screen.getByRole("alert", { name: "There is a problem" });
    expect(within(summary).getByText("Active UAN must contain exactly 12 digits.")).toBeTruthy();
    expect(within(summary).getByText("Duplicate UAN must contain exactly 12 digits.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Review and confirm merge" }));
    expect(within(summary).getByText("Enter an officer note of up to 1,000 characters.")).toBeTruthy();
    expect(command).not.toHaveBeenCalled();
  });

  it("requires distinct UANs before asking for confirmation", () => {
    show();
    fireEvent.change(screen.getByLabelText("Active UAN"), { target: { value: merge.active_uan } });
    fireEvent.change(screen.getByLabelText("Duplicate UAN"), { target: { value: merge.active_uan } });
    fireEvent.change(screen.getByLabelText("Officer note"), { target: { value: merge.note } });
    fireEvent.click(screen.getByRole("button", { name: "Review and confirm merge" }));
    expect(within(screen.getByRole("alert", { name: "There is a problem" })).getByText("Duplicate UAN must differ from the active UAN.")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("confirms the duplicate UAN, then posts with the step-up token and shows the result", async () => {
    vi.mocked(command).mockResolvedValue({ data: merge, meta: { correlation_id: "test", as_of: "2026-10-05" } });
    show(); fill();
    fireEvent.click(screen.getByRole("button", { name: "Review and confirm merge" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirm UAN merge" });
    expect(within(dialog).getByText(`merge-uan: ${merge.duplicate_uan}`)).toBeTruthy();
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm merge" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("POST", "/api/v1/office/uan-merges", {
      active_uan: merge.active_uan, duplicate_uan: merge.duplicate_uan, note: merge.note,
    }, { stepUpToken: "confirmed-token" }));
    const live = screen.getByText("UAN merge recorded").closest("[aria-live]");
    expect(live?.textContent).toContain(`Duplicate UAN ${merge.duplicate_uan} is closed`);
    expect(live?.textContent).toContain("AL-1, AL-2");
    expect(live?.textContent).toContain("Balances associated with the linked accounts follow the active UAN");
  });

  it("renders active and duplicate UAN, time, and officer in the responsive table", async () => {
    vi.mocked(api).mockResolvedValue({ data: [merge], meta: { correlation_id: "test", as_of: "2026-10-05" } });
    show();
    const table = await screen.findByRole("table");
    expect(table.classList.contains("responsive-table")).toBe(true);
    expect(within(table).getByText(merge.active_uan)).toBeTruthy();
    expect(within(table).getByText(merge.duplicate_uan)).toBeTruthy();
    expect(within(table).getByText("officer-1")).toBeTruthy();
    expect(table.querySelectorAll("td[data-label]")).toHaveLength(4);
    expect(table.textContent).toContain("5 Oct 2026");
  });

  it("shows API problem details such as the field whose identity differs", async () => {
    vi.mocked(command).mockRejectedValue(new ApiError({ type: "/problems/identity-mismatch", status: 422,
      title: "Identity mismatch", detail: "Date of birth does not match between active and duplicate UAN" }));
    show(); fill();
    fireEvent.click(screen.getByRole("button", { name: "Review and confirm merge" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Confirm merge" }));
    expect(await screen.findByText("Date of birth does not match between active and duplicate UAN")).toBeTruthy();
  });
});
