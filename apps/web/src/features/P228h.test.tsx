import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api, command, rupees } from "../api/client";
import "../i18n";
import { ReceiptPage } from "./member/ReceiptPage";
import { VerifyReceiptPage } from "./public/VerifyReceiptPage";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: vi.fn(),
  command: vi.fn(),
}));

vi.mock("qrcode", () => ({
  default: {
    toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,fake-qr-code-data"),
  },
  toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,fake-qr-code-data"),
}));

afterEach(cleanup);

const wrap = (node: ReactNode, initialEntries: string[]) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>{node}</MemoryRouter>
    </QueryClientProvider>
  );

describe("P2.28h Claim Receipt Page", () => {
  it("shows the receipt fields, large monospace code and QR image", async () => {
    vi.mocked(api).mockResolvedValueOnce({
      data: {
        claim_id: "CLM-1234ABCD",
        form_type: "31",
        claim_label: "Illness advance",
        amount_paise: 5000000,
        filed_on: "2026-10-04",
        state: "UNDER_REVIEW",
        member_name: "Demo Member",
        uan_masked: "********1234",
        employer: "Demo Enterprise",
        code: "ABCDE23456",
        verify_path: "/public/receipts/verify?claim=CLM-1234ABCD&code=ABCDE23456",
      },
      meta: { correlation_id: "c-1", api_version: "v1", source: "poc", as_of: "" },
    });

    wrap(
      <Routes>
        <Route path="/member/claims/:claimId/receipt" element={<ReceiptPage />} />
      </Routes>,
      ["/member/claims/CLM-1234ABCD/receipt"]
    );

    expect(await screen.findByRole("heading", { name: "Claim receipt" })).toBeTruthy();
    expect(screen.getByText("CLM-1234ABCD")).toBeTruthy();
    expect(screen.getByText(/Illness advance/)).toBeTruthy();
    expect(screen.getByText(rupees(5000000))).toBeTruthy();
    expect(screen.getByText("04/10/2026")).toBeTruthy();
    expect(screen.getByText("Demo Member")).toBeTruthy();
    expect(screen.getByText("********1234")).toBeTruthy();
    expect(screen.getByText("Demo Enterprise")).toBeTruthy();
    expect(screen.getByText("ABCDE23456")).toBeTruthy();

    const qrImg = await screen.findByAltText("QR code to verify this receipt");
    expect(qrImg).toBeTruthy();
    expect(screen.getByRole("button", { name: "Print or save" })).toBeTruthy();
  });
});

describe("P2.28h Verify Receipt Page", () => {
  it("prefills claim and code from query string, verifies genuine and not-verified answers", async () => {
    wrap(
      <Routes>
        <Route path="/public/receipts/verify" element={<VerifyReceiptPage />} />
      </Routes>,
      ["/public/receipts/verify?claim=CLM-1234ABCD&code=ABCDE23456"]
    );

    const claimInput = screen.getByLabelText("Claim ID") as HTMLInputElement;
    const codeInput = screen.getByLabelText("Verification code") as HTMLInputElement;

    expect(claimInput.value).toBe("CLM-1234ABCD");
    expect(codeInput.value).toBe("ABCDE23456");

    // 1. Genuine flow
    vi.mocked(api).mockResolvedValueOnce({
      data: { challenge_id: "demo-ch-1", prompt: "What is 4 + 3?" },
      meta: { correlation_id: "", api_version: "v1", source: "", as_of: "" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Get one-use demo question" }));
    expect(await screen.findByText("What is 4 + 3?")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("What is 4 + 3?"), { target: { value: "7" } });

    vi.mocked(command).mockResolvedValueOnce({
      data: {
        genuine: true,
        claim_id: "CLM-1234ABCD",
        form_type: "31",
        amount_paise: 5000000,
        filed_on: "2026-10-04",
        state: "UNDER_REVIEW",
      },
      meta: { correlation_id: "", api_version: "v1", source: "", as_of: "" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Check receipt" }));

    expect(await screen.findByText("Genuine receipt")).toBeTruthy();
    expect(screen.getByText("31")).toBeTruthy();
    expect(screen.getByText(rupees(5000000))).toBeTruthy();
    expect(screen.getByText("04/10/2026")).toBeTruthy();

    // 2. Not-verified flow
    vi.mocked(api).mockResolvedValueOnce({
      data: { challenge_id: "demo-ch-2", prompt: "What is 5 + 5?" },
      meta: { correlation_id: "", api_version: "v1", source: "", as_of: "" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Get one-use demo question" }));
    expect(await screen.findByText("What is 5 + 5?")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("What is 5 + 5?"), { target: { value: "10" } });

    vi.mocked(command).mockResolvedValueOnce({
      data: { genuine: false },
      meta: { correlation_id: "", api_version: "v1", source: "", as_of: "" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Check receipt" }));

    expect(await screen.findByText("This receipt could not be verified")).toBeTruthy();
    expect(screen.queryByText("Genuine receipt")).toBeNull();
  });
});
