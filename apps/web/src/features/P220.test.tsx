import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { MenuSearch } from "../components/MenuSearch";
import { RoleNav } from "../components/RoleNav";
import { homeFor, menusFor } from "../data/navigation";
import { defaultLayout, useNavLayout } from "../data/navLayout";
import "../i18n";

afterEach(() => { cleanup(); window.localStorage.clear(); });
function Where() { const l = useLocation(); return <p data-testid="where">{l.pathname}{l.hash}</p>; }
function show(page: ReactElement, at = "/") {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[at]}><Routes><Route path="*" element={<>{page}<Where /></>} /></Routes></MemoryRouter></QueryClientProvider>);
}

it("puts the menu at the side for office roles and on top for members, and remembers a choice", () => {
  expect(defaultLayout("fo.apfc")).toBe("side");
  expect(defaultLayout("ho.cpfc")).toBe("side");
  expect(defaultLayout("member")).toBe("top");
  expect(defaultLayout("employer.owner")).toBe("top");
  const { result } = renderHook(() => useNavLayout("member"));
  expect(result.current[0]).toBe("top");
  act(() => result.current[1]("side"));
  expect(result.current[0]).toBe("side");
  expect(window.localStorage.getItem("epfo.nav-layout")).toBe("side");
  expect(renderHook(() => useNavLayout("fo.apfc")).result.current[0]).toBe("side");
});

it("draws the side menu as a tree: the current page's group open, others folded, a filter across all", () => {
  show(<RoleNav role="fo.apfc" layout="side" />, "/office/inquiries");
  const compliance = screen.getByRole("button", { name: /Establishments & compliance/ });
  expect(compliance.getAttribute("aria-expanded")).toBe("true");                          // holds the current page
  expect(screen.getByRole("link", { name: "Inspections and 7A inquiries" }).getAttribute("aria-current")).toBe("page");
  const claims = screen.getByRole("button", { name: /Claims & settlement/ });
  expect(claims.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(claims);
  expect(claims.getAttribute("aria-expanded")).toBe("true");
  expect(screen.queryByText("PAST ACCUM BULK TRANSFER")).toBeNull();                       // items not built: hidden by default
  fireEvent.click(screen.getByLabelText("Show items not built"));
  expect(screen.getByText("PAST ACCUM BULK TRANSFER")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Filter the menu"), { target: { value: "recovery" } });
  expect(screen.getByRole("link", { name: "Recovery certificates" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Inspections and 7A inquiries" })).toBeNull();
});

it("finds a screen with Ctrl+K and opens it with Enter", () => {
  show(<MenuSearch role="fo.apfc" />, "/office/work-queue");
  fireEvent.keyDown(document, { key: "k", ctrlKey: true });
  const dialog = screen.getByRole("dialog", { name: "Find a screen" });
  const box = within(dialog).getByRole("combobox");
  fireEvent.change(box, { target: { value: "legal" } });
  expect(within(dialog).getAllByRole("option")[0].textContent).toContain("Legal cases");
  fireEvent.keyDown(box, { key: "Enter" });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByTestId("where").textContent).toBe("/office/legal");
  fireEvent.click(screen.getByRole("button", { name: /Find a screen/ }));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "zzzz" } });
  expect(screen.getByText("No screen matches")).toBeTruthy();
});

it("gives the empty headings a destination or a reason", () => {
  const employer = menusFor("employer.owner");
  expect(employer.find((g) => g.label === "Admin")?.items?.map((i) => i.to)).toEqual(["/employer#people-operator", "/employer/establishment#config-change-heading"]);
  const eec = employer.find((g) => g.label === "EEC-2026/VISHWAS")?.items ?? [];
  expect(eec[0].to).toBe("/employer/returns#vishwas-heading");
  expect(eec[1].to).toBe("/employer/returns#eec-heading");
  const office = (role: string) => menusFor(role).find((g) => g.label === "Office")?.items ?? [];
  expect(office("fo.da_compliance").find((i) => i.label === "Dashboard")?.to).toBe(homeFor("fo.da_compliance"));   // the role's own home
  expect(office("fo.pro").find((i) => i.label === "Services")?.to).toBe("/office/pro-counter");
  expect(office("fo.apfc").find((i) => i.label === "Admin")?.note).toMatch(/HR/);
});

it("lets anyone enlarge the text in steps up to 150%, remembered, and back to the default", async () => {
  const { TextSizeControl } = await import("../components/TextSizeControl");
  render(<TextSizeControl />);
  const larger = screen.getByRole("button", { name: "Larger text" });
  expect(screen.getByRole("button", { name: "Smaller text" })).toHaveProperty("disabled", true);
  fireEvent.click(larger); fireEvent.click(larger);
  expect(document.documentElement.style.fontSize).toBe("130%");
  expect(window.localStorage.getItem("epfo.text-size")).toBe("130");
  fireEvent.click(larger);
  expect(document.documentElement.style.fontSize).toBe("150%");
  expect(larger).toHaveProperty("disabled", true);
  expect(screen.getByText("Text size 150%")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Default text size" }));
  expect(document.documentElement.style.fontSize).toBe("");
});
