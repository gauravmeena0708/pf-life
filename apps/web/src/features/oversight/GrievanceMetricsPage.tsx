import { useQuery } from "@tanstack/react-query";

import { api, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface Metrics {
  as_of: string; source: string;
  offices: { office_id: string; registered: number; resolved: number; pending: number; escalations: number; resolved_within_sla_pct: number | null }[];
  pending_by_tier: Record<string, number>;
  by_category: Record<string, number>;
}

/** Grievance pendency and resolution within service standards (Journey C5), built only from events. */
export function GrievanceMetricsPage() {
  const q = useQuery({ queryKey: ["grievance-metrics"], queryFn: () => api<Envelope<Metrics>>("/api/v1/monitoring/grievances"), retry: false, refetchInterval: 5000 });
  const m = q.data?.data;
  const total = m?.offices.reduce((a, o) => ({ registered: a.registered + o.registered, pending: a.pending + o.pending, escalations: a.escalations + o.escalations }),
    { registered: 0, pending: 0, escalations: 0 });
  return (
    <section className="stack" aria-labelledby="gm-heading">
      <PageHeader id="gm-heading" eyebrow="Monitoring · Journey C" title="Grievance metrics"
        description={m ? `As of ${new Date(m.as_of).toLocaleString("en-IN")} · source: ${m.source}` : "Pendency, escalations and resolution within the service standard."}
        current="Grievance metrics" />
      <ProblemMessage error={q.error} />
      {m && total ? (
        <>
          <section className="metrics" aria-label="Totals">
            <div><span>Registered</span><strong>{total.registered}</strong></div>
            <div><span>Pending</span><strong>{total.pending}</strong></div>
            <div><span>Escalations</span><strong>{total.escalations}</strong></div>
            <div><span>Pending by tier</span><strong>{Object.entries(m.pending_by_tier).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}</strong></div>
          </section>
          <section className="card stack" aria-labelledby="gm-offices"><h2 id="gm-offices">By office</h2>
            <div className="table-scroll"><table>
              <thead><tr><th scope="col">Office</th><th scope="col" className="numeric">Registered</th><th scope="col" className="numeric">Resolved</th><th scope="col" className="numeric">Pending</th><th scope="col" className="numeric">Escalations</th><th scope="col" className="numeric">Resolved within SLA</th></tr></thead>
              <tbody>{m.offices.map((o) => (
                <tr key={o.office_id}><td>{o.office_id}</td><td className="numeric">{o.registered}</td><td className="numeric">{o.resolved}</td><td className="numeric">{o.pending}</td>
                  <td className="numeric">{o.escalations}</td><td className="numeric">{o.resolved_within_sla_pct === null ? "—" : `${o.resolved_within_sla_pct}%`}</td></tr>
              ))}</tbody>
            </table></div>
          </section>
          <section className="card stack" aria-labelledby="gm-cat"><h2 id="gm-cat">By category</h2>
            <ul className="activity-ranking">{Object.entries(m.by_category).map(([k, v]) => <li key={k}><span>{k.replaceAll("_", " ").toLowerCase()}</span><strong>{v}</strong></li>)}</ul>
          </section>
        </>
      ) : null}
    </section>
  );
}
