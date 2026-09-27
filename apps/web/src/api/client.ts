/** Fetch wrapper for the gateway. Cookies only (no tokens in the browser); CSRF header on changes. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  correlation_id?: string;
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

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (!["GET", "HEAD"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  const res = await fetch(path, { ...init, method, headers, credentials: "include" });
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
