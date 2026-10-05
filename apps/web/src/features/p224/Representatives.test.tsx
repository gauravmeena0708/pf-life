import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MyRepresentatives, RepresentativeHome } from "./Representatives";
import { api, setActingFor } from "../../api/client";

beforeEach(() => { sessionStorage.clear(); vi.stubGlobal("fetch", vi.fn()); });
afterEach(() => vi.unstubAllGlobals());
const reply = (data: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify({ data }), headers: new Headers() });

describe("representatives", () => {
  it("grants selected scopes and lists the authorisation", async () => {
    const fetcher = vi.mocked(fetch);
    fetcher.mockResolvedValueOnce(reply([]) as Response).mockResolvedValueOnce(reply({ grant_id: "REP-1" }) as Response)
      .mockResolvedValueOnce(reply([{ grant_id: "REP-1", representative_subject: "rep-sub", relation: "AGENT", scopes: ["VIEW_PROFILE"], valid_until: "2027-01-01", state: "ACTIVE" }]) as Response);
    render(<MyRepresentatives />);
    fireEvent.change(screen.getByLabelText("Representative username"), { target: { value: "rep-demo" } });
    fireEvent.click(screen.getByLabelText("View member profile"));
    fireEvent.change(screen.getByLabelText("Valid until"), { target: { value: "2027-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Authorise representative" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "rep-sub" })).toBeTruthy());
    const body = JSON.parse(String(fetcher.mock.calls[1][1]?.body));
    expect(body).toMatchObject({ representative_username: "rep-demo", scopes: ["VIEW_PROFILE"], relation: "AGENT" });
  });

  it("chooses and clears the active member", async () => {
    vi.mocked(fetch).mockResolvedValue(reply([{ grant_id: "REP-1", member_name: "Member A", member_subject: "member-a", relation: "AGENT", scopes: ["VIEW_PASSBOOK"], valid_until: "2027-01-01" }]) as Response);
    render(<RepresentativeHome />);
    fireEvent.click(await screen.findByRole("button", { name: "Act for this member" }));
    expect(sessionStorage.getItem("epfo-acting-for")).toBe("REP-1");
    fireEvent.click(screen.getByRole("button", { name: "Stop acting for a member" }));
    expect(sessionStorage.getItem("epfo-acting-for")).toBeNull();
  });

  it("adds acting header only to member routes", async () => {
    vi.mocked(fetch).mockResolvedValue(reply([]) as Response);
    setActingFor("REP-1");
    await api("/api/v1/members/me/passbook");
    await api("/api/v1/representatives/me/members");
    const calls = vi.mocked(fetch).mock.calls;
    expect((calls[0][1]?.headers as Headers).get("X-Acting-For")).toBe("REP-1");
    expect((calls[1][1]?.headers as Headers).has("X-Acting-For")).toBe(false);
  });
});
