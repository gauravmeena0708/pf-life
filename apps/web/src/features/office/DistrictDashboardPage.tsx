import { useQuery } from "@tanstack/react-query";

import { api, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface DistrictDashboard {
  office_id: string; as_of: string; note: string;
  claims: { pending: number; settled_last_30_days: number; pending_over_sla: number; returned_payments: number };
  grievances: { open: number; resolved_last_30_days: number; resolved_within_sla_pct: number | null; escalated_open: number };
  establishments: { with_filings: number; defaulting: number; paid_late_last_12_months: number };
}
export function DistrictDashboardPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const authorised = session.data?.stakeholder === "do.incharge";
  const dashboard = useQuery({ queryKey: ["district-dashboard"], enabled: authorised, retry: false,
    queryFn: () => api<Envelope<DistrictDashboard>>("/api/v1/do/dashboards") });
  const data = dashboard.data?.data;
  const metrics = data ? [
    ["Pending claims", data.claims.pending], ["Claims settled in the last 30 days", data.claims.settled_last_30_days],
    ["Claims pending over SLA", data.claims.pending_over_sla], ["Returned payments", data.claims.returned_payments],
    ["Open grievances", data.grievances.open], ["Grievances resolved in the last 30 days", data.grievances.resolved_last_30_days],
    ["Grievances resolved within SLA", data.grievances.resolved_within_sla_pct === null ? "fewer than 5 resolved" : `${data.grievances.resolved_within_sla_pct}%`],
    ["Escalated open grievances", data.grievances.escalated_open], ["Establishments with filings", data.establishments.with_filings],
    ["Defaulting establishments", data.establishments.defaulting], ["Establishments paid late in the last 12 months", data.establishments.paid_late_last_12_months],
  ] as const : [];
  return <section className="stack" aria-labelledby="do-dashboard-heading">
    <PageHeader id="do-dashboard-heading" eyebrow="District Office" title="District dashboard"
      description="Claims, grievances and establishment filing metrics for the demonstration." current="District dashboard" />
    <ProblemMessage error={session.error ?? dashboard.error} />
    {session.isLoading || dashboard.isLoading ? <p role="status">Loading dashboard…</p> : null}
    {session.data && !authorised ? <p className="pending-notice">This service is available to the District Office in charge.</p> : null}
    {data ? <><p>Office {data.office_id} · As of {data.as_of}</p>
      <section className="metrics" aria-label="District metrics">{metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</section>
      <p className="muted">{data.note}</p>
    </> : null}
  </section>;
}
