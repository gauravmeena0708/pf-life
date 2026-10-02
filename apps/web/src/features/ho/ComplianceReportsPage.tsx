import { useQuery } from "@tanstack/react-query";

import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

/** HO's view of compliance: e-Proceedings (inquiries by section and stage, overdue orders, disposal, legal cases) and recovery
 *  (certified, realised by mode, outstanding, stayed, in instalments, older than a year). */
interface Proceedings { as_of: string; inquiries: number; pending: number; disposed_this_month: number; average_days_to_order: number | null;
  by_section: Record<string, Record<string, number>>; pending_by_office: Record<string, number>;
  orders_overdue: { case_id: string; diary_no: string; establishment: string; officer_rank: string; order_due_at: string }[]; legal_cases: Record<string, number> }
interface Recovery { as_of: string; certificates: number; open: number; certified_paise: number; realised_paise: number; outstanding_paise: number;
  realised_by_mode_paise: Record<string, number>; stayed_paise: number; in_instalments: number; older_than_a_year: number; by_state: Record<string, number> }

function Figures({ items }: { items: [string, string | number][] }) {
  return <dl className="kv">{items.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>;
}

export function ComplianceReportsPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const proceedings = useQuery({ queryKey: ["ho-proceedings"], enabled: role === "ho.compliance", retry: false,
    queryFn: () => api<Envelope<Proceedings>>("/api/v1/ho/reports/proceedings") });
  const recovery = useQuery({ queryKey: ["ho-recovery"], enabled: ["ho.compliance", "ho.recovery"].includes(role), retry: false,
    queryFn: () => api<Envelope<Recovery>>("/api/v1/ho/reports/recovery") });
  const p = proceedings.data?.data; const r = recovery.data?.data;
  return <section className="stack" aria-labelledby="ho-compliance-heading">
    <PageHeader id="ho-compliance-heading" eyebrow="Head Office" title="Proceedings and recovery" current="Proceedings and recovery"
      description="Inquiries under 7A, 7C, 14B and 26B across the offices, the orders overdue, and what recovery has realised." />
    <ProblemMessage error={proceedings.error} /><ProblemMessage error={recovery.error} />
    {p ? <section className="card stack" aria-labelledby="proc-heading"><h2 id="proc-heading">e-Proceedings</h2>
      <Figures items={[["Inquiries", p.inquiries], ["Pending", p.pending], ["Orders this month", p.disposed_this_month],
        ["Average days to order", p.average_days_to_order ?? "—"], ["Orders overdue", p.orders_overdue.length]]} />
      <div className="table-scroll"><table><caption>By section and stage</caption><thead><tr><th scope="col">Section</th><th scope="col">Stages</th></tr></thead>
        <tbody>{Object.entries(p.by_section).map(([section, states]) => <tr key={section}><th scope="row">{section}</th>
          <td>{Object.entries(states).map(([s, n]) => `${s} ${n}`).join(" · ")}</td></tr>)}</tbody></table></div>
      {p.orders_overdue.length ? <><h3>Orders overdue</h3><ul>{p.orders_overdue.map((o) => <li key={o.case_id}>{o.diary_no} · {o.establishment} · {o.officer_rank} ·
        due {new Date(o.order_due_at).toLocaleDateString("en-IN")}</li>)}</ul></> : null}
      {Object.keys(p.legal_cases).length ? <p className="muted small">Legal cases: {Object.entries(p.legal_cases).map(([k, n]) => `${k} ${n}`).join(" · ")}</p> : null}
    </section> : null}
    {r ? <section className="card stack" aria-labelledby="rec-heading"><h2 id="rec-heading">Recovery</h2>
      <Figures items={[["Certificates", r.certificates], ["Open", r.open], ["Certified", rupees(r.certified_paise)], ["Realised", rupees(r.realised_paise)],
        ["Outstanding", rupees(r.outstanding_paise)], ["Stayed by courts", rupees(r.stayed_paise)], ["In instalments", r.in_instalments], ["Older than a year", r.older_than_a_year]]} />
      <p>Realised by mode: {Object.entries(r.realised_by_mode_paise).map(([m, v]) => `${m.replace("_", " ")} ${rupees(v)}`).join(" · ") || "nothing yet"}</p>
    </section> : null}
  </section>;
}
