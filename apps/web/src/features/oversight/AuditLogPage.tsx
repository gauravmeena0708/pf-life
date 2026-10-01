import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, getSession, type Envelope } from "../../api/client";
import { InternalParas } from "../audit/InternalParas";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface AuditItem { seq: number; event_id: string; event_type: string; producer: string; aggregate_type: string; aggregate_id: string;
  correlation_id: string; occurred_at: string; payload: Record<string, unknown>; prev_hash: string; hash: string }
interface AuditPage { items: AuditItem[]; chain: { valid: boolean; checked: number; head?: string; broken_at_seq?: number } }

/** Append-only audit log with hash-chain verification and correlation tracing (Journey C5, interface 16). */
export function AuditLogPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const [filter, setFilter] = useState({ event_type: "", aggregate_id: "" });
  const [correlation, setCorrelation] = useState<string | null>(null);
  const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v)).toString();
  const log = useQuery({ queryKey: ["audit", params], queryFn: () => api<Envelope<AuditPage>>(`/api/v1/audit/events?limit=200${params ? `&${params}` : ""}`), retry: false });
  const trail = useQuery({ queryKey: ["audit-correlation", correlation], enabled: !!correlation, retry: false,
    queryFn: () => api<Envelope<{ items: AuditItem[] }>>(`/api/v1/audit/correlations/${correlation}`) });
  const chain = log.data?.data.chain;

  function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setFilter({ event_type: String(f.get("event_type")).trim(), aggregate_id: String(f.get("aggregate_id")).trim() });
  }

  const table = (items: AuditItem[]) => (
    <div className="table-scroll"><table>
      <thead><tr><th scope="col">#</th><th scope="col">Event</th><th scope="col">Producer</th><th scope="col">Aggregate</th><th scope="col">Correlation</th><th scope="col">Payload</th><th scope="col">Hash</th></tr></thead>
      <tbody>{items.map((i) => (
        <tr key={i.seq}>
          <td>{i.seq}</td><td>{i.event_type}<br /><span className="muted small">{i.occurred_at}</span></td><td>{i.producer}</td>
          <td>{i.aggregate_type}<br /><code>{i.aggregate_id}</code></td>
          <td><button type="button" className="lookup-link" onClick={() => setCorrelation(i.correlation_id)}>{i.correlation_id.slice(0, 8)}</button></td>
          <td><code className="small">{JSON.stringify(i.payload).slice(0, 140)}</code></td>
          <td><code title={`previous ${i.prev_hash}`}>{i.hash.slice(0, 12)}</code></td>
        </tr>
      ))}</tbody>
    </table></div>
  );

  return (
    <section className="stack" aria-labelledby="audit-heading">
      <PageHeader id="audit-heading" eyebrow="Audit · append-only" title="Audit log"
        description="Every business event, in order. Rows cannot be changed or deleted, and each row carries the hash of the one before."
        current="Audit log" />
      <ProblemMessage error={log.error} />
      {chain ? (
        <p role="status" className={chain.valid ? "ok" : "problem"}>
          {chain.valid ? `Hash chain verified: ${chain.checked} events, head ${chain.head?.slice(0, 16)}…`
            : `Hash chain BROKEN at event #${chain.broken_at_seq}: the log was altered outside the application.`}
        </p>
      ) : null}
      <form className="card search-input-row" onSubmit={search}>
        <div className="form-row">
          <label>Event type<input name="event_type" placeholder="e.g. GrievanceEscalated.v1" /></label>
          <label>Aggregate ID<input name="aggregate_id" placeholder="e.g. GRV-… or CLM-…" /></label>
        </div>
        <button type="submit" className="primary">Filter</button>
      </form>
      {correlation ? (
        <section className="card stack" aria-labelledby="corr-heading">
          <div className="section-heading"><h2 id="corr-heading">Correlation {correlation}</h2><button type="button" onClick={() => setCorrelation(null)}>Close</button></div>
          <ProblemMessage error={trail.error} />
          {trail.data ? table(trail.data.data.items) : null}
        </section>
      ) : null}
      {session.data?.stakeholder === "ho.audit" ? <InternalParas role="ho.audit" /> : null}
      <section className="card stack" aria-labelledby="events-heading"><h2 id="events-heading">Events</h2>{log.data ? table(log.data.data.items) : null}</section>
    </section>
  );
}
