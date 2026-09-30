import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { getMyPermissions, getSession } from "../api/client";
import { PersonaSwitcher } from "../components/PersonaSwitcher";
import { RoleNav } from "../components/RoleNav";
import { StatusBadge } from "../components/StatusBadge";
import { leaveSession } from "../data/demoAuth";
import { INTERFACES, STAKEHOLDERS, TOTALS } from "../data/interfaces";
import interfacesSource from "../data/interfaces.ts?raw";
import { JOURNEYS } from "../data/journeys";
import { homeFor } from "../data/navigation";
import { PERSONAS, PERSONA_GROUPS } from "../data/personas";
import generated from "../data/system-map.generated.json";
import "../i18n";
import { Home } from "../pages/Home";
import { InterfacePage } from "../pages/InterfacePage";
import { SystemMapPage } from "../pages/SystemMapPage";

vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(), getSession: vi.fn(), getMyPermissions: vi.fn(),
}));
let clients: QueryClient[];
beforeEach(() => {
  vi.clearAllMocks();
  clients = [];
  vi.mocked(getSession).mockResolvedValue({ authenticated: false });
});
afterEach(() => { cleanup(); clients.forEach((client) => client.clear()); });
function mount(element: ReactElement, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{element}</MemoryRouter></QueryClientProvider>);
}

it("shows generated totals, one headline and all eight guided journeys on home", () => {
  mount(<Home />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  const totals = within(screen.getByRole("list", { name: "What's built" }));
  expect(totals.getByText(`${generated.totals.interfaces} interfaces`)).toBeTruthy();
  expect(totals.getByText(`${generated.totals.stakeholders_with_access} of ${generated.totals.stakeholders} roles with access`)).toBeTruthy();
  expect(totals.getByText(`${generated.totals.endpoints.W} working endpoints`)).toBeTruthy();
  expect(totals.getByText(`${generated.totals.endpoints.M} simulated`)).toBeTruthy();
  expect(totals.getByText(`${generated.totals.endpoints.P} planned`)).toBeTruthy();
  expect(totals.getByText(`${generated.totals.personas} demo personas`)).toBeTruthy();
  expect(screen.getAllByRole("article")).toHaveLength(8);
  JOURNEYS.forEach((journey) => {
    const card = screen.getByRole("article", { name: journey.title });
    journey.personas.forEach((username) => {
      const persona = PERSONAS.find((item) => item.username === username)!;
      expect(within(card).getByText(persona.label, { selector: "li" })).toBeTruthy();
    });
    const first = PERSONAS.find((persona) => persona.username === journey.personas[0])!;
    const link = within(card).getByRole("link", { name: `Start as ${first.label}` });
    expect(link.getAttribute("href")).toContain(`persona=${first.username}`);
    expect(new URL(link.getAttribute("href")!, "http://localhost").searchParams.get("return_to")).toBe(homeFor(first.role));
  });
});

it("filters system map by coverage and interface, role, activity and persona description searches", () => {
  mount(<SystemMapPage />);
  expect(screen.getAllByRole("article")).toHaveLength(TOTALS.interfaces);
  for (const status of ["Working", "Mock", "Planned"]) {
    fireEvent.change(screen.getByLabelText("Coverage status"), { target: { value: status } });
    expect(screen.getAllByRole("article")).toHaveLength(INTERFACES.filter((item) => item.coverage === status).length);
  }
  fireEvent.change(screen.getByLabelText("Coverage status"), { target: { value: "" } });
  const search = screen.getByLabelText("Search interfaces and roles");
  fireEvent.change(search, { target: { value: "vigilance" } });
  expect(screen.getByRole("article", { name: "Vigilance" })).toBeTruthy();
  expect(screen.getByRole("article", { name: "CAIU" })).toBeTruthy();
  expect(screen.queryByRole("article", { name: "Member" })).toBeNull();
  const member = STAKEHOLDERS.member;
  for (const term of [member.name, member.activities[0].does, "claims wait for the employer's attestation"]) {
    fireEvent.change(search, { target: { value: term } });
    expect(screen.getByRole("article", { name: "Member" })).toBeTruthy();
  }
  fireEvent.change(search, { target: { value: "no matching interface xyz" } });
  expect(screen.queryAllByRole("article")).toHaveLength(0);
  expect(screen.getByText("No interfaces match these filters.")).toBeTruthy();
});

it("combines group and persona filters on the same role", () => {
  mount(<SystemMapPage />);
  fireEvent.change(screen.getByLabelText("Stakeholder group"), { target: { value: STAKEHOLDERS.member.group } });
  fireEvent.click(screen.getByLabelText("Has a demo persona"));
  screen.getAllByRole("article").forEach((card) => {
    const ids = Array.from(card.querySelectorAll("summary code")).map((code) => code.textContent!);
    expect(ids.length).toBeGreaterThan(0);
    ids.forEach((id) => {
      expect(STAKEHOLDERS[id].group).toBe(STAKEHOLDERS.member.group);
      expect(STAKEHOLDERS[id].personas.some((username) => PERSONAS.some((persona) => persona.username === username))).toBe(true);
    });
  });
});

it("expands named roles to show activities and persona login links", () => {
  mount(<SystemMapPage />);
  const card = screen.getByRole("article", { name: "Member" });
  const summary = within(card).getByText(STAKEHOLDERS.member.name).closest("summary")!;
  fireEvent.click(summary);
  expect(summary.parentElement?.hasAttribute("open")).toBe(true);
  expect(within(card).getByText(STAKEHOLDERS.member.activities[0].does)).toBeTruthy();
  const link = within(card).getByRole("link", { name: "Try as Member A" });
  expect(link.getAttribute("href")).toBe("/auth/login?persona=member-a&return_to=%2Fmember");
});

it("reads interface and stakeholder lists directly from the generator", () => {
  expect(INTERFACES).toEqual(generated.interfaces);
  expect(STAKEHOLDERS).toEqual(generated.stakeholders);
  expect(TOTALS).toEqual(generated.totals);
  expect(interfacesSource).toContain('import generated from "./system-map.generated.json"');
  expect(interfacesSource).not.toMatch(/stakeholders:\s*\[/);
});

it("gives every persona a valid group and a useful description", () => {
  PERSONAS.forEach((persona) => {
    expect(PERSONA_GROUPS).toContain(persona.group);
    expect(persona.description.trim().length).toBeGreaterThan(20);
  });
  JOURNEYS.forEach((journey) => journey.personas.forEach((username) => expect(PERSONAS.some((persona) => persona.username === username)).toBe(true)));
});

it("searches the grouped picker and closes it with Escape, returning focus", () => {
  mount(<PersonaSwitcher />);
  const summary = screen.getByText("Sign in (demo)");
  fireEvent.click(summary);
  fireEvent.change(screen.getByLabelText("Search demo personas"), { target: { value: "attestation" } });
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(screen.getByRole("button", { name: /Member F.*claims wait.*member/ })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Members and public" })).toBeTruthy();
  expect(screen.getByText("Demo@2026!")).toBeTruthy();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(summary.closest("details")?.hasAttribute("open")).toBe(false);
  expect(document.activeElement).toBe(summary);
});

it("has one Public services link and a System map link for all roles", () => {
  for (const role of [undefined, "member", "ho.security"]) {
    const view = mount(<RoleNav role={role} />);
    expect(screen.getAllByRole("link", { name: "Public services" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "System map" }).getAttribute("href")).toBe("/system-map");
    view.unmount();
  }
});

it("uses a top-level logout POST with CSRF and the next persona", () => {
  document.cookie = "epfo-csrf=test-token";
  const submit = vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(() => undefined);
  leaveSession("security-analyst", homeFor("ho.security"));
  const form = document.body.querySelector<HTMLFormElement>('form[action^="/auth/logout"]')!;
  expect(form.method).toBe("post");
  const params = new URL(form.action).searchParams;
  expect(params.get("next_persona")).toBe("security-analyst");
  expect(params.get("return_to")).toBe("/security/activity");
  expect(form.querySelector<HTMLInputElement>('[name="csrf_token"]')?.value).toBe("test-token");
  expect(submit).toHaveBeenCalledOnce();
  form.remove(); submit.mockRestore();
  document.cookie = "epfo-csrf=; Max-Age=0";
});

it("opens the workspace for any authenticated role", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "zo.rpfc1_audit" });
  mount(<Home />);
  await waitFor(() => expect(screen.getByRole("link", { name: "Open your workspace" }).getAttribute("href")).toBe(homeFor("zo.rpfc1_audit")));
});

it("keeps signed-in permission details alongside the shared interface role list", async () => {
  vi.mocked(getSession).mockResolvedValue({ authenticated: true, stakeholder: "member" });
  vi.mocked(getMyPermissions).mockResolvedValue({ data: { stakeholder: "member", endpoints: [{ endpoint: "demo.endpoint", status: "W", scope: "own", step_up: false }] } });
  mount(<Routes><Route path="/i/:slug" element={<InterfacePage />} /></Routes>, "/i/member");
  expect(screen.getByText(INTERFACES.find((item) => item.slug === "member")!.purpose)).toBeTruthy();
  expect(screen.getByText(STAKEHOLDERS.member.name)).toBeTruthy();
  await waitFor(() => expect(screen.getByText("demo.endpoint")).toBeTruthy());
});

it("labels Mock as Simulated without changing its data value", () => {
  mount(<StatusBadge status="Mock" />);
  expect(screen.getByText(/Simulated/)).toBeTruthy();
  expect(INTERFACES.some((item) => item.coverage === "Mock")).toBe(true);
});
