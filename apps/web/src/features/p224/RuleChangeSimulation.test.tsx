import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RuleChangeSimulation } from "./RuleChangeSimulation";

vi.mock("../../api/client", () => ({ api: vi.fn().mockResolvedValue({ data: { sample_size: 4, total_change_paise: 0, bands: [{ band: "lower", member_count: 4, min_change_paise: 0, median_change_paise: 0, max_change_paise: 0, gain_count: 0, lose_count: 0 }] } }) }));

describe("RuleChangeSimulation", () => {
  it("submits proposed rules and announces the result", async () => {
    render(<RuleChangeSimulation />);
    fireEvent.change(screen.getByLabelText("Interest rate (basis points)"), { target: { value: "850" } });
    fireEvent.click(screen.getByRole("button", { name: "Run simulation" }));
    expect(await screen.findByText(/Total effect: 0 paise/)).toBeTruthy();
  });
});
