/** Fetch wrapper for the gateway. Cookies only (no tokens in the browser); CSRF header on changes. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  errors?: (string | { field?: string; message?: string; msg?: string; loc?: (string | number)[] })[];
  correlation_id?: string;
  reason_codes?: string[];
  action?: string;
  resource_id?: string;
}

export class ApiError extends Error {
  constructor(public problem: Problem) {
    super(problem.title);
  }
}

function csrfToken(): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith("epfo-csrf="))
    ?.split("=")[1];
}

const ACTING_FOR_KEY = "epfo-acting-for";

export function setActingFor(grantId: string | null): void {
  if (grantId) sessionStorage.setItem(ACTING_FOR_KEY, grantId);
  else sessionStorage.removeItem(ACTING_FOR_KEY);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (/^\/api\/v1\/members\/me(?:\/|$)/.test(path)) {
    const grantId = sessionStorage.getItem(ACTING_FOR_KEY);
    if (grantId) headers.set("X-Acting-For", grantId);
  }
  if (!["GET", "HEAD"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  const send = (requestHeaders: Headers) => fetch(path, { ...init, method, headers: requestHeaders, credentials: "include" });
  let res = await send(headers);
  if (res.status === 428 && !headers.has("X-Step-Up-Token") && !path.includes("/step-up-challenges")) {
    const challenge = await res.clone().json().catch(() => null) as Problem | null;
    // P2.28: only a risk-based challenge (it names its reasons and its exact binding) is confirmed here and retried
    // once; a route that always needs confirmation keeps its page's own dialog, which knows the action and amount.
    if (challenge?.type === "/problems/step-up-required" && challenge.reason_codes?.length && challenge.action && challenge.resource_id) {
      const { confirmRiskStepUp } = await import("../features/p228/Prompt");
      const token = await confirmRiskStepUp(challenge);
      if (token) {
        headers.set("X-Step-Up-Token", token);
        res = await send(headers);
      }
    }
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const problem: Problem =
      body && typeof body === "object" && "title" in body
        ? body
        : { type: "/problems/http", title: res.statusText || "Request failed", status: res.status };
    problem.correlation_id ??= res.headers.get("X-Correlation-Id") ?? undefined;
    throw new ApiError(problem);
  }
  return body as T;
}

export interface Session {
  authenticated: boolean;
  subject?: string;
  stakeholder?: string;
  persona_label?: string;
  expires_at?: string;
}

export interface Grant {
  endpoint: string;
  status: "W" | "M" | "P" | "?";
  scope: string;
  step_up: boolean;
}

export const getSession = () => api<Session>("/auth/session");
export const getMyPermissions = () =>
  api<{ data: { stakeholder: string; endpoints: Grant[] } }>("/api/v1/security/me/permissions");

export interface CommandOptions {
  stepUpToken?: string;
  idempotencyKey?: string;
  ifMatch?: string | number;
  establishmentId?: string;
}

/** POST/PUT/PATCH with the headers commands need (init.md §3.3, §6.3). */
export function command<T>(method: string, path: string, body?: unknown, opts: CommandOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.stepUpToken) headers["X-Step-Up-Token"] = opts.stepUpToken;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  if (opts.ifMatch !== undefined) headers["If-Match"] = String(opts.ifMatch);
  if (opts.establishmentId) headers["X-Establishment-Id"] = opts.establishmentId;
  return api<T>(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
}

export interface Envelope<T> {
  data: T;
  meta: { correlation_id: string; as_of: string };
}

export function rupees(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(paise / 100);
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/** The rule set in force today (public figures). Screens derive samples and choices from it, never from constants. */
export interface CurrentPolicy {
  rule_version: string;
  effective_from: string;
  contribution: { epf_employee_rate_bp: number; eps_rate_bp: number; eps_wage_ceiling_paise: number; edli_wage_ceiling_paise: number };
  claim_types: Record<string, { form_type: string; label: string; plain_rule: string }>;
  grievance_categories: string[];
  scheduled: { rule_version: string; effective_from: string }[];
}
export const getCurrentPolicy = () => api<Envelope<CurrentPolicy>>("/api/v1/public/policy/current");
