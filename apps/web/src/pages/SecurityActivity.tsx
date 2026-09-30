import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, Envelope, getSession } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { ProblemMessage } from "../components/ProblemMessage";
import { SecurityIncidents } from "../features/oversight/SecurityIncidents";

type ActivityEvent = {
  at: string; method: string; route: string; status: number; duration_ms: number;
  peer_ip: string; peer_kind: string; actor: string; stakeholder: string;
  query_fields: string[]; body_fields: string[]; body_bytes: number | null;
  lookup_fingerprint: string | null; search_mode: string | null;
  rate_decision: string; challenge_decision: string | null; correlation_id: string;
};
type Activity = {
  window_seconds: number; retention_seconds: number; history_limit: number; gateway_peer_note: string;
  metrics: { requests_5m: number; requests_1m: number; blocked_5m: number; challenge_failures_5m: number; server_errors_5m: number };
  top_routes: { route: string; requests: number }[];
  top_peers: { peer_ip: string; requests: number }[];
  events: ActivityEvent[];
};

function activitySummary(event: ActivityEvent): string {
  const fields = [...event.query_fields.map((field) => `query.${field}`), ...event.body_fields.map((field) => `body.${field}`)];
  return fields.length ? fields.join(", ") : event.body_bytes ? `${event.body_bytes} body bytes` : "No request fields";
}

export function SecurityActivity() {
  const [blockedOnly, setBlockedOnly] = useState(false);
  const [routeFilter, setRouteFilter] = useState("");
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const authorised = session.data?.stakeholder === "ho.security";
  const activity = useQuery({
    queryKey: ["security", "request-activity"],
    queryFn: () => api<Envelope<Activity>>( "/api/v1/security/request-activity"),
    enabled: authorised,
    refetchInterval: 15_000,
    retry: false,
  });
  const data = activity.data?.data;
  const visible = data?.events.filter((item) => (!blockedOnly || item.status === 403 || item.status === 429)
    && (!routeFilter || item.route === routeFilter)) || [];

  return <div className="stack security-workspace">
    <PageHeader eyebrow="Interface 17 · security analyst" title="Request activity"
      description="Recent gateway traffic, rates and challenge decisions for the synthetic demonstration."
      current="Security activity">
      {authorised && <button type="button" onClick={() => void activity.refetch()} disabled={activity.isFetching}>Refresh now</button>}
    </PageHeader>
    <ProblemMessage error={session.error} />
    {session.isLoading && <p>Checking access…</p>}
    {!session.isLoading && !authorised && <div className="card"><h2>Security role required</h2><p>Switch to the security analyst demo persona to view gateway activity.</p></div>}
    {authorised && <>
      <ProblemMessage error={activity.error} />
      <SecurityIncidents />
      {!data && !activity.error && <p>Loading recent activity…</p>}
      {data && <>
        <section className="metrics" aria-label="Five minute activity summary">
          <div><span>Requests · 5 min</span><strong>{data.metrics.requests_5m}</strong></div>
          <div><span>Requests · 1 min</span><strong>{data.metrics.requests_1m}</strong></div>
          <div><span>Blocked · 5 min</span><strong>{data.metrics.blocked_5m}</strong></div>
          <div><span>Challenge failures</span><strong>{data.metrics.challenge_failures_5m}</strong></div>
          <div><span>Server errors</span><strong>{data.metrics.server_errors_5m}</strong></div>
        </section>
        <section className="activity-columns">
          <div className="card stack"><h2>Busiest routes</h2>{data.top_routes.length ? <ol className="activity-ranking">{data.top_routes.map((item) => <li key={item.route}><code>{item.route}</code><strong>{item.requests}</strong></li>)}</ol> : <p className="muted">No recent traffic.</p>}</div>
          <div className="card stack"><h2>Busiest gateway peers</h2>{data.top_peers.length ? <ol className="activity-ranking">{data.top_peers.map((item) => <li key={item.peer_ip}><code>{item.peer_ip}</code><strong>{item.requests}</strong></li>)}</ol> : <p className="muted">No recent traffic.</p>}</div>
        </section>
        <section className="card stack" aria-labelledby="recent-requests">
          <div className="section-heading"><div><p className="eyebrow">Latest {data.events.length} of up to {data.history_limit}</p><h2 id="recent-requests">Recent requests</h2></div><span className="muted small">Refreshes every 15 seconds</span></div>
          <div className="form-row"><label>Route<select value={routeFilter} onChange={(event) => setRouteFilter(event.target.value)}><option value="">All routes</option>
            {[...new Set(data.events.map((item) => item.route))].sort().map((route) => <option key={route} value={route}>{route}</option>)}</select></label>
            <label className="check-row"><input type="checkbox" checked={blockedOnly} onChange={(event) => setBlockedOnly(event.target.checked)} />Blocked only (403 / 429)</label></div>
          <div className="table-scroll"><table><thead><tr><th>When</th><th>Request</th><th>Who</th><th>Gateway peer</th><th className="numeric">Result</th><th>Request shape</th></tr></thead>
            <tbody>{visible.map((item) => <tr key={item.correlation_id}>
              <td><time dateTime={item.at}>{new Date(item.at).toLocaleTimeString()}</time><br /><small>{item.duration_ms} ms</small></td>
              <td><strong>{item.method}</strong> <code>{item.route}</code></td>
              <td>{item.stakeholder}<br /><code className="small">{item.actor}</code></td>
              <td><code>{item.peer_ip}</code></td>
              <td className="numeric"><span className={item.status >= 400 ? "status-alert" : "status-good"}>{item.status}</span><br /><small>{item.rate_decision}{item.challenge_decision ? ` · proof ${item.challenge_decision}` : ""}</small></td>
              <td><span className="small">{activitySummary(item)}</span>
                {item.search_mode && <div className="small">Mode: {item.search_mode}</div>}
                {item.lookup_fingerprint && <div className="small">Lookup fingerprint: <code>{item.lookup_fingerprint}</code></div>}
                <div className="small muted">Correlation: <code>{item.correlation_id}</code></div></td>
            </tr>)}</tbody></table></div>
          {!visible.length && <p className="muted">No requests match these filters.</p>}
        </section>
        <p className="muted small">{data.gateway_peer_note} Request values, tokens, OTPs and full bodies are excluded. This Redis demo retains up to {data.history_limit} events for at most 24 hours.</p>
      </>}
    </>}
  </div>;
}
