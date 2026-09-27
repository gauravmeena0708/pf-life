import { render, screen } from "@testing-library/react";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("shows status as text, not colour alone", () => {
    render(<StatusBadge status="P" />);
    expect(screen.getByText(/Planned/)).toBeTruthy();
  });

  it("labels definition-pending endpoints", () => {
    render(<StatusBadge status="?" />);
    expect(screen.getByText(/Definition pending/)).toBeTruthy();
  });
});
