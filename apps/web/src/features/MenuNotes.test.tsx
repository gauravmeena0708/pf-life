import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { RoleNav } from "../components/RoleNav";
import { menusFor } from "../data/navigation";
import "../i18n";

const items = (role: string) => menusFor(role).flatMap((g) => g.items ?? []);

it("links menu items whose screens are built", () => {
  expect(items("member")).toContainEqual(expect.objectContaining({ label: "Change Password", to: "/member/security#password-heading" }));
  expect(items("claimant")).toContainEqual(expect.objectContaining({ label: "Composite claim (CCF)", to: "/claimant#file-heading" }));
  expect(items("pensioner")).toContainEqual(expect.objectContaining({ label: "Know Your Pension Payee Bank", to: "/pensioner#monthly-pension-heading" }));
});

it("says why an item has no screen: planned, awaiting EPFO's definition, or not in the POC", () => {
  const oic = items("fo.oic");
  expect(oic.find((i) => i.label === "PAST ACCUM BULK TRANSFER")?.note).toMatch(/^Planned/);
  expect(oic.find((i) => i.label === "Reco - ECR Vs VDR")?.note).toMatch(/EPFO's definition/);
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><RoleNav role="fo.oic" /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: /Establishments & compliance/ }));
  const planned = screen.getByText("PAST ACCUM BULK TRANSFER").closest(".nav-unavailable") as HTMLElement;
  expect(planned.getAttribute("title")).toMatch(/^Planned/);
  expect(within(planned).getByText("Planned")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Receipts & reconciliation/ }));
  const undefinedItem = screen.getByText("Reco - ECR Vs VDR").closest(".nav-unavailable") as HTMLElement;
  expect(undefinedItem.getAttribute("title")).toMatch(/EPFO's definition/);
  expect(within(undefinedItem).getByText("Not in POC")).toBeTruthy();
});
