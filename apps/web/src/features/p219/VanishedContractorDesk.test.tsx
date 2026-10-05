import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, afterEach, vi } from "vitest";
import { VanishedContractorDesk } from "./VanishedContractorDesk";

afterEach(cleanup);

describe("VanishedContractorDesk (EPF Act s.8A)", () => {
  it("renders the assessment desk with proper semantic HTML and labels", () => {
    render(<VanishedContractorDesk role="fo.apfc" />);

    expect(screen.getByRole("heading", { level: 1, name: /Vanished Contractor Dues Assessment/i })).toBeTruthy();
    expect(screen.getByLabelText(/Compliance Case ID/i)).toBeTruthy();
    expect(screen.getByLabelText(/Contractor \/ Agency Name/i)).toBeTruthy();
    expect(screen.getByLabelText(/Contractor EPF Code Number/i)).toBeTruthy();
    expect(screen.getByLabelText(/Contractor Traceability Status/i)).toBeTruthy();
    expect(screen.getByLabelText(/Assessed Dues Amount/i)).toBeTruthy();
    expect(screen.getByLabelText(/Inquiry Findings and Legal Reasoning/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Assess Dues Against Principal Employer/i })).toBeTruthy();
  });

  it("blocks assessment against principal when contractor has EPF code and is traceable (s.8A exception)", () => {
    render(<VanishedContractorDesk role="fo.apfc" />);

    fireEvent.change(screen.getByLabelText(/Compliance Case ID/i), { target: { value: "CMP-001" } });
    fireEvent.change(screen.getByLabelText(/Contractor \/ Agency Name/i), { target: { value: "M/s Traceable Security" } });
    fireEvent.change(screen.getByLabelText(/Contractor EPF Code Number/i), { target: { value: "EST-CTR-9999" } });
    fireEvent.change(screen.getByLabelText(/Contractor Traceability Status/i), { target: { value: "true" } });
    fireEvent.change(screen.getByLabelText(/Assessed Dues Amount/i), { target: { value: "45000" } });
    fireEvent.change(screen.getByLabelText(/Inquiry Findings and Legal Reasoning/i), { target: { value: "Traceable coded contractor" } });

    fireEvent.click(screen.getByRole("button", { name: /Assess Dues Against Principal Employer/i }));

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Cannot assess principal employer: A contractor with an EPF code number who is traceable is liable itself/i)).toBeTruthy();
  });

  it("successfully passes order against principal when contractor is untraceable under EPF Act s.8A", () => {
    const onOrderPassed = vi.fn();
    render(<VanishedContractorDesk role="fo.apfc" onOrderPassed={onOrderPassed} />);

    fireEvent.change(screen.getByLabelText(/Compliance Case ID/i), { target: { value: "CMP-002" } });
    fireEvent.change(screen.getByLabelText(/Contractor \/ Agency Name/i), { target: { value: "M/s Vanished Security" } });
    fireEvent.change(screen.getByLabelText(/Contractor Traceability Status/i), { target: { value: "false" } });
    fireEvent.change(screen.getByLabelText(/Assessed Dues Amount/i), { target: { value: "45000" } });
    fireEvent.change(screen.getByLabelText(/Inquiry Findings and Legal Reasoning/i), { target: { value: "Untraceable at site" } });

    fireEvent.click(screen.getByRole("button", { name: /Assess Dues Against Principal Employer/i }));

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(/Order successfully passed under Section 7A read with Section 8A against principal employer/i)).toBeTruthy();
    expect(screen.getByText(/The principal employer has the statutory right to recover this amount from the contractor/i)).toBeTruthy();
    expect(onOrderPassed).toHaveBeenCalledWith(
      expect.objectContaining({
        case_id: "CMP-002",
        total_paise: 4500000,
        contractor: expect.objectContaining({
          contractor_name: "M/s Vanished Security",
          traceable: false,
        }),
      })
    );
  });

  it("toggles language between English and complete Hindi", () => {
    render(<VanishedContractorDesk role="fo.apfc" />);

    const langBtn = screen.getByRole("button", { name: "हिन्दी" });
    fireEvent.click(langBtn);

    expect(screen.getByRole("heading", { level: 1, name: /लापता ठेकेदार बकाया निर्धारण/i })).toBeTruthy();
    expect(screen.getByLabelText(/अनुपालन मामला संख्या/i)).toBeTruthy();

    const enBtn = screen.getByRole("button", { name: "English" });
    fireEvent.click(enBtn);

    expect(screen.getByRole("heading", { level: 1, name: /Vanished Contractor Dues Assessment/i })).toBeTruthy();
  });
});
