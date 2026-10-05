import { api } from "../../api/client";
import { confirmRiskStepUp } from "./Prompt";

vi.mock("./Prompt", () => ({ confirmRiskStepUp: vi.fn().mockResolvedValue("confirmed-token") }));

it("opens confirmation for a risk 428 and retries the original request once", async () => {
  const response = (status: number, body: object) => new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });
  const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(response(428, {
    type: "/problems/step-up-required", title: "Confirm this action first", status: 428,
    reason_codes: ["new-device"], action: "risk:get:/members/me/nominations",
    resource_id: "/members/me/nominations",
  })).mockResolvedValueOnce(response(200, { data: [] }));
  const result = await api<{ data: unknown[] }>("/api/v1/members/me/nominations");
  expect(result.data).toEqual([]);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(new Headers(fetcher.mock.calls[1][1]?.headers).get("X-Step-Up-Token")).toBe("confirmed-token");
  fetcher.mockRestore();
});

it("leaves a catalogue 428 without risk reasons to the page's own confirmation", async () => {
  const response = (status: number, body: object) => new Response(JSON.stringify(body), { status });
  vi.mocked(confirmRiskStepUp).mockClear();
  const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(response(428, {
    type: "/problems/step-up-required", title: "Confirm this action first", status: 428,
  }));
  await expect(api("/api/v1/members/me/contact-details", { method: "PATCH" })).rejects.toBeTruthy();
  expect(confirmRiskStepUp).not.toHaveBeenCalled();
  expect(fetcher).toHaveBeenCalledTimes(1);
  fetcher.mockRestore();
});
