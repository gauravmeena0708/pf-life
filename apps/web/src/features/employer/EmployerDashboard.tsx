import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

interface EmployerDashboardData {
  establishment_id: string; as_of: string; returns: { wage_month: string; status: string; due_date: string; paid_on: string | null }[];
  alerts: { kind: string; message: string; link: string }[]; counts: Record<string, number>;
  see_also: { label?: string; link: string }[]; note: string;
}
export function EmployerDashboard() {
  const { t } = useTranslation();
  const dashboard = useQuery({ queryKey: ["employer-dashboard"], retry: false,
    queryFn: () => api<Envelope<EmployerDashboardData>>("/api/v1/employers/me/dashboard") });
  const data = dashboard.data?.data;
  return <section className="card stack" aria-labelledby="employer-dashboard-heading"><h2 id="employer-dashboard-heading">Employer dashboard</h2>
    <ProblemMessage error={dashboard.error} />
    {dashboard.isLoading ? <p role="status">Loading dashboard…</p> : null}
    {data ? <><p>{data.establishment_id} · As of {data.as_of}</p>
      <div className="metrics" aria-label="Return counts">{Object.entries(data.counts).map(([label, count]) => <div key={label}><span>{statusLabel(label, t)}</span><strong>{count}</strong></div>)}</div>
      <h3>Alerts</h3>{data.alerts.length ? <ul>{data.alerts.map((alert, index) => <li key={`${alert.kind}:${index}`}><Link to={alert.link}>{alert.message}</Link></li>)}</ul> : <p className="muted">No alerts.</p>}
      <h3>Returns</h3><div className="table-scroll"><table><thead><tr><th scope="col">Wage month</th><th scope="col">Status</th><th scope="col">Due date</th><th scope="col">Paid on</th></tr></thead>
        <tbody>{data.returns.map((item) => <tr key={item.wage_month}><th scope="row">{item.wage_month}</th><td>{statusLabel(item.status, t)}</td><td>{item.due_date}</td><td>{item.paid_on ?? "—"}</td></tr>)}</tbody>
      </table></div>{!data.returns.length ? <p className="muted">No returns recorded.</p> : null}
      {data.see_also.length ? <nav aria-label="Related employer services"><ul>{data.see_also.map((item) => <li key={item.link}><Link to={item.link}>{item.label ?? item.link}</Link></li>)}</ul></nav> : null}
      <p className="muted">{data.note}</p>
    </> : null}
  </section>;
}
