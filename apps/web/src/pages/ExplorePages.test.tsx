import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import "../i18n";
import { ACTIVITIES, STAKEHOLDERS, type Activity } from "../data/interfaces";
import { Home } from "./Home";
import { layout, LifecyclesPage } from "./LifecyclesPage";
import { ManualsPage } from "./ManualsPage";
import { StakeholdersPage } from "./StakeholdersPage";

vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), getSession: vi.fn().mockResolvedValue({ authenticated: false }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function show(page: ReactElement, at = "/") {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[at]}>{page}</MemoryRouter></QueryClientProvider>);
}
const act = (id: string, next: string[] = []): Activity => ({ id, flow: "F99", actor: "member", does: id, next, status: "BUILT", endpoints: 1, src: "" });

it("links the home page to the system map, stakeholders, lifecycles and manuals", async () => {
  show(<Home />);
  for (const [name, to] of [["System map", "/system-map"], ["Stakeholders", "/stakeholders"], ["Lifecycles", "/lifecycles"], ["User manuals", "/manuals"]])
    expect((await screen.findByRole("link", { name })).getAttribute("href")).toBe(to);
});

it("arranges stakeholders by hierarchy and shows a role's login and activities", () => {
  show(<StakeholdersPage />, "/stakeholders");
  const chart = screen.getByRole("group", { name: "EPFO hierarchy" });
  for (const tier of ["Governance and oversight", "Head Office", "Zonal Offices", "Regional Offices", "District Offices"])
    expect(within(chart).getByRole("heading", { name: new RegExp(tier) })).toBeTruthy();
  expect(Object.values(STAKEHOLDERS).some((s) => s.name.includes("**"))).toBe(false);          // no Markdown in names
  fireEvent.click(within(chart).getByRole("button", { name: /^Enforcement Officer/ }));
  const detail = screen.getByRole("complementary");
  expect(within(detail).getByRole("heading", { name: "Enforcement Officer" })).toBeTruthy();
  expect(within(detail).getByText(/ro-eo/)).toBeTruthy();
  expect(within(detail).getByRole("link", { name: /Enforcement Officer inspection/ }).getAttribute("href")).toMatch(/^\/lifecycles\?flow=F06&activity=/);
});

it("lays a lifecycle out by its chain of next steps, placing a lone start just before its successor", () => {
  const { placed, back } = layout([act("a", ["b"]), act("b", ["c"]), act("c", ["b"]), act("x", ["c"])]);
  const layer = Object.fromEntries(placed.map((p) => [p.act.id, p.layer]));
  expect(layer).toEqual({ a: 0, b: 1, c: 2, x: 1 });
  expect(back.has("c>b")).toBe(true);                                                           // the loop is drawn dashed
});

it("draws the compliance lifecycle and opens a step", () => {
  show(<LifecyclesPage />, "/lifecycles?flow=F06");
  expect(screen.getByRole("heading", { name: /Compliance, inspection/ })).toBeTruthy();
  const network = screen.getByRole("group", { name: /Network of Compliance/ });
  const steps = ACTIVITIES.filter((a) => a.flow === "F06");
  expect(within(network).getAllByRole("button")).toHaveLength(steps.length);
  fireEvent.click(within(network).getByRole("button", { name: /Process the inspection report/ }));
  const detail = screen.getByRole("complementary");
  expect(within(detail).getByText("F06.report_process")).toBeTruthy();
  expect(within(detail).getByRole("link", { name: /Section Supervisor puts the report up/ })).toBeTruthy();
});

it("lists the published manuals, or says how to publish them", async () => {
  vi.stubGlobal("fetch", vi.fn(async (path: string) => ({ ok: true, json: async () => path.endsWith("catalogue.json")
    ? { status: "verified", manuals: [{ name: "claim-review-member", title: "Form 31 claim", role: "Member", steps: 9, kind: "role", case_ids: ["CLM-1"] }] }
    : { run: "RUN-1", published_at: "2026-10-02T07:00:00Z" } })));
  show(<ManualsPage />, "/manuals");
  expect((await screen.findByRole("link", { name: "Member" })).getAttribute("href")).toBe("/manuals/manuals/claim-review-member.html");
  expect(screen.getByText(/RUN-1/)).toBeTruthy();
  cleanup();
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, json: async () => ({}) })));
  show(<ManualsPage />, "/manuals");
  expect(await screen.findByRole("heading", { name: "No manuals are published yet" })).toBeTruthy();
});
