import { useQuery } from "@tanstack/react-query";

import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

type Row = Record<string, unknown>;
interface Claims { offices: Row[]; totals: Row; source: string[]; as_of: string }
interface Contributions { wage_months: Row[]; totals: Row; source: string[] }
interface Freshness { sources: { source: string; last_event_type: string; last_event_at: string; events_seen: number; lag_seconds: number; status: string }[] }
interface Zone { zone_id: string; claims: { offices: Row[] }; grievances: { offices: Row[] } }
interface PublicStats { claims_settled: number | null; contributions_posted_paise: number | null; grievances_resolved: number | null; note: string }

const CAN = {
  claims: ["fo.oic", "fo.rpfc1", "gov.mole", "ho.cpfc"], contributions: ["fo.rpfc1", "gov.mole", "ho.cpfc"],
  freshness: ["ho.cpfc"], stats: ["gov.mole"], zone: ["zo.acc"],
};
const label = (k: string) => k.replaceAll("_", " ").replace(" paise", "");
const show = (k: string, v: unknown) => v === null || v === undefined ? "—" : k.endsWith("_paise") ? rupees(Number(v))
  : typeof v === "object" ? Object.entries(v as Row).map(([a, b]) => `${a}: ${b}`).join(", ") || "—"
  : typeof v === "number" && !Number.isInteger(v) ? v.toFixed(2) : String(v);

function Table({ rows, first }: { rows: Row[]; first: string }) {
  if (!rows.length) return <p className="muted">No data yet.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="table-scroll"><table>
      <thead><tr>{cols.map((c) => <th key={c} scope="col" className={c === first ? "" : "numeric"}>{label(c)}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c} className={c === first ? "" : "numeric"}>{show(c, r[c])}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

/** Tier-3 read models (dashboards) built only from events; each panel shows only what the role may see. */
export function DashboardsPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const useDash = <T,>(key: string, path: string, allowed: string[]) =>
    useQuery({ queryKey: ["dash", key], enabled: allowed.includes(role), retry: false, refetchInterval: 10000,
               queryFn: () => api<Envelope<T>>(path) });
  const claims = useDash<Claims>("claims", "/api/v1/monitoring/claims", CAN.claims);
  const contributions = useDash<Contributions>("contributions", "/api/v1/monitoring/contributions", CAN.contributions);
  const freshness = useDash<Freshness>("freshness", "/api/v1/monitoring/data-freshness", CAN.freshness);
  const stats = useDash<PublicStats>("stats", "/api/v1/public/statistics", CAN.stats);
  const zone = useDash<Zone>("zone", "/api/v1/zo/dashboards", CAN.zone);

  return (
    <section className="stack" aria-labelledby="dash-heading">
      <PageHeader id="dash-heading" eyebrow="Monitoring · read models" title="Dashboards"
        description="Built only from business events (tier-3 read models); no dashboard reads another service's database."
        current="Dashboards" />
      {[claims, contributions, freshness, stats, zone].map((x, i) => <ProblemMessage key={i} error={x.error} />)}
      {claims.data ? <section className="card stack"><h2>Claims by office</h2>
        <Table rows={claims.data.data.offices} first="office_id" />
        <p className="muted small">Totals: {Object.entries(claims.data.data.totals).map(([k, v]) => `${label(k)} ${show(k, v)}`).join(" · ")}</p>
      </section> : null}
      {contributions.data ? <section className="card stack"><h2>Contributions by wage month</h2>
        <Table rows={contributions.data.data.wage_months} first="wage_month" /></section> : null}
      {freshness.data ? <section className="card stack"><h2>Data freshness</h2>
        <Table rows={freshness.data.data.sources.map(({ source, status, last_event_type, events_seen, lag_seconds }) =>
          ({ source, status, last_event_type, events_seen, lag_seconds: Math.round(lag_seconds) }))} first="source" /></section> : null}
      {stats.data ? <section className="card stack"><h2>Public statistics</h2>
        <section className="metrics passbook-metrics">
          <div><span>Claims settled</span><strong>{show("n", stats.data.data.claims_settled)}</strong></div>
          <div><span>Contributions posted</span><strong>{show("x_paise", stats.data.data.contributions_posted_paise)}</strong></div>
          <div><span>Grievances resolved</span><strong>{show("n", stats.data.data.grievances_resolved)}</strong></div>
        </section><p className="muted small">{stats.data.data.note}</p></section> : null}
      {zone.data ? <section className="card stack"><h2>Zone {zone.data.data.zone_id}</h2>
        <h3>Claims</h3><Table rows={zone.data.data.claims.offices} first="office_id" />
        <h3>Grievances</h3><Table rows={zone.data.data.grievances.offices} first="office_id" /></section> : null}
    </section>
  );
}
