import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface ReportCard {
  establishment_id: string; as_of: string; note: string; remitted_paise: number; counts: Record<string, number>;
  months: { wage_month: string; due_date: string; status: string; paid_on: string | null; days_late: number | null }[];
}
const statuses: Record<string, string> = { FILED_AND_PAID_ON_TIME: "Filed and paid on time", PAID_LATE: "Paid late", FILED_NOT_PAID: "Filed, not paid", NOT_FILED: "Not filed" };

export function EReportCardPage() {
  const { estId } = useParams();
  const report = useQuery({ queryKey: ["public-e-report-card", estId], enabled: !!estId, retry: false,
    queryFn: () => api<Envelope<ReportCard>>(`/api/v1/public/establishments/${encodeURIComponent(estId!)}/e-report-card`) });
  const data = report.data?.data;
  return <section className="stack" aria-labelledby="e-report-card-heading">
    <PageHeader id="e-report-card-heading" eyebrow="Public services · synthetic POC" title="e-Report Card"
      description={`Filing and payment history for ${estId}.`} current="e-Report Card" parent={{ label: "Establishment search", to: "/public" }} />
    <ProblemMessage error={report.error} />
    {report.isLoading ? <p role="status">Loading e-Report Card…</p> : null}
    {data ? <section className="card stack" aria-label="Establishment filing history">
      <p><strong>{data.establishment_id}</strong> · As of {data.as_of}</p><p className="muted">{data.note}</p>
      <dl className="profile-grid"><div><dt>Total remitted</dt><dd>{rupees(data.remitted_paise)}</dd></div>
        {Object.entries(data.counts).map(([state, count]) => <div key={state}><dt>{statuses[state] ?? state}</dt><dd>{count}</dd></div>)}
      </dl>
      <div className="table-scroll"><table><thead><tr><th scope="col">Wage month</th><th scope="col">Due date</th><th scope="col">Status</th><th scope="col">Paid on</th><th scope="col">Days late</th></tr></thead>
        <tbody>{data.months.map((month) => <tr key={month.wage_month}><th scope="row">{month.wage_month}</th><td>{month.due_date}</td>
          <td>{statuses[month.status] ?? month.status}</td><td>{month.paid_on ?? "Not paid"}</td><td>{month.days_late ?? "—"}</td></tr>)}</tbody>
      </table></div>
    </section> : null}
  </section>;
}
