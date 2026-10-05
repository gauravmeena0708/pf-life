import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../../api/client";
import { InterestSustainability } from "./InterestSustainability";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual("../../api/client");
  return {
    ...actual,
    api: vi.fn(),
  };
});

const mockResult = {
  financial_year: "2025-26",
  total_book_value_paise: 300_000_000,
  income_paise: 22_000_000,
  sensitivity: {
    minus_50_bp_income_paise: 20_500_000,
    plus_50_bp_income_paise: 23_500_000,
  },
  proposed_rate_bp: 825,
  liability_paise: 20_000_000,
  surplus_paise: 2_000_000,
  verdict: "SUSTAINABLE",
  break_even_rate_bp: 908,
  current_declared_rate_bp: 825,
  current_income_paise: 22_000_000,
  current_liability_paise: 20_000_000,
  current_surplus_paise: 2_000_000,
  current_verdict: "SUSTAINABLE",
  by_asset_class: [
    {
      asset_class: "GOVT_SECURITIES",
      book_value_paise: 200_000_000,
      yield_bp: 720,
      income_paise: 14_400_000,
    },
    {
      asset_class: "DEBT",
      book_value_paise: 100_000_000,
      yield_bp: 760,
      income_paise: 7_600_000,
    },
  ],
  yield_assumptions: [
    {
      asset_class: "GOVT_SECURITIES",
      yield_bp: 720,
      label: "Central govt securities (illustrative)",
      illustrative: true,
    },
    {
      asset_class: "DEBT",
      yield_bp: 760,
      label: "Corporate bonds (illustrative)",
      illustrative: true,
    },
  ],
};

describe("InterestSustainability component", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("evaluates sustainability and displays income, liability, surplus, break-even rate, and sensitivity", async () => {
    vi.mocked(api).mockResolvedValueOnce({ data: mockResult, meta: { correlation_id: "c1", as_of: "2026-09-30" } });

    render(<InterestSustainability />);

    expect((screen.getByLabelText("Financial Year") as HTMLInputElement).value).toBe("2025-26");
    expect((screen.getByLabelText(/Proposed Interest Rate \(basis points\)/) as HTMLInputElement).value).toBe("825");

    fireEvent.click(screen.getByRole("button", { name: "Evaluate Sustainability" }));

    await waitFor(() => {
      expect(api).toHaveBeenCalledWith(
        "/api/v1/ho/finance/interest-sustainability",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ financial_year: "2025-26", proposed_rate_bp: 825 }),
        })
      );
    });

    // Check key metrics rendered
    expect(await screen.findByText("Sustainability Assessment")).toBeTruthy();
    expect(screen.getByTestId("sustain-verdict-badge").textContent).toBe("SUSTAINABLE");
    expect(screen.getByText("908 bp")).toBeTruthy();
    expect(screen.getByText(/Yield Sensitivity/)).toBeTruthy();

    // Check asset class table rendered
    expect(screen.getAllByText("GOVT_SECURITIES").length).toBeGreaterThan(0);
    expect(screen.getAllByText("DEBT").length).toBeGreaterThan(0);

    // Check yield assumptions section rendered
    expect(screen.getByRole("heading", { name: "Yield Assumptions (Illustrative)" })).toBeTruthy();
  });

  it("handles editing and saving a yield assumption", async () => {
    vi.mocked(api).mockResolvedValueOnce({ data: mockResult, meta: { correlation_id: "c1", as_of: "2026-09-30" } });

    render(<InterestSustainability />);
    fireEvent.click(screen.getByRole("button", { name: "Evaluate Sustainability" }));
    await screen.findByText("Sustainability Assessment");

    // Click edit on the first yield assumption
    const editButtons = screen.getAllByRole("button", { name: "Edit" });
    fireEvent.click(editButtons[0]);

    const yieldInput = screen.getByLabelText("Yield for GOVT_SECURITIES") as HTMLInputElement;
    expect(yieldInput.value).toBe("720");

    fireEvent.change(yieldInput, { target: { value: "800" } });

    vi.mocked(api).mockResolvedValueOnce({
      data: { asset_class: "GOVT_SECURITIES", yield_bp: 800, illustrative: true },
      meta: { correlation_id: "c2", as_of: "2026-09-30" },
    });
    vi.mocked(api).mockResolvedValueOnce({ data: { ...mockResult, income_paise: 22_800_000 }, meta: { correlation_id: "c3", as_of: "2026-09-30" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(api).toHaveBeenCalledWith(
        "/api/v1/ho/finance/yield-assumptions/GOVT_SECURITIES",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ yield_bp: 800 }),
        })
      );
    });

    expect(await screen.findByText("Yield assumption updated successfully.")).toBeTruthy();
  });

  it("shows error alert on 422 without positions", async () => {
    const error = new ApiError({
      status: 422,
      title: "No fund positions are known for the EPF fund.",
      type: "/problems/no-fund-positions",
    });
    vi.mocked(api).mockRejectedValueOnce(error);

    render(<InterestSustainability />);
    fireEvent.click(screen.getByRole("button", { name: "Evaluate Sustainability" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("No fund positions are known for the EPF fund.");
  });

  it("switches language between English and Hindi", async () => {
    render(<InterestSustainability />);

    expect(screen.getByText("EPF Interest Sustainability Model")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "hi" } });

    expect(screen.getByText("ईपीएफ ब्याज स्थिरता मॉडल")).toBeTruthy();
    expect(screen.getByRole("button", { name: "स्थिरता का मूल्यांकन करें" })).toBeTruthy();
  });
});
