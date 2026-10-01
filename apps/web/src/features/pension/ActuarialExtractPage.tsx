import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";

type Row = { record_id: string; category: string; age_years: number; gender: string | null; pension_start_year: number | null;
  monthly_pension_paise: number | null; service_months: number | null; status: string };
type Extract = { as_of: string; rows: Row[]; aggregates: { category: string; age_band: string; count: number }[]; rule_version: string; note: string };
const columns: (keyof Row)[] = ["record_id", "category", "age_years", "gender", "pension_start_year", "monthly_pension_paise", "service_months", "status"];
const csvCell = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
export function rowsCsv(rows: Row[]) { return [columns.join(","), ...rows.map((row) => columns.map((key) => csvCell(row[key])).join(","))].join("\r\n") + "\r\n"; }

export function ActuarialExtractPage() {
  const { t } = useTranslation();
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = session.data?.stakeholder === "ho.actuarial";
  const extract = useQuery({ queryKey: ["actuarial-extract", asOf], enabled: allowed && !!asOf, retry: false,
    queryFn: () => api<Envelope<Extract>>(`/api/v1/ho/actuarial/extracts?as_of=${encodeURIComponent(asOf)}`) });
  const data = extract.data?.data;
  function download() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([rowsCsv(data.rows)], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `actuarial-extract-${data.as_of}.csv`; link.click();
    URL.revokeObjectURL(url);
  }
  return <section className="stack" aria-labelledby="actuarial-heading">
    <PageHeader id="actuarial-heading" eyebrow="Head office" title="Actuarial extract"
      description="EPS valuation figures without direct identifiers." current="Actuarial extract" />
    <ProblemMessage error={session.error ?? extract.error} />
    {session.data && !allowed ? <p className="pending-notice">This service is available to the actuarial division.</p> : null}
    {allowed ? <section className="card stack"><label>As-of date<input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label>
      {extract.isLoading ? <p role="status">Loading actuarial extract…</p> : null}
      {data ? <><p className="muted small">This extract has no direct identifiers. {data.note}</p>
        <p>Rule version: {data.rule_version}</p><div className="actions"><button type="button" onClick={download}>Download CSV</button></div>
        <h2>Aggregates</h2><div className="table-scroll"><table><thead><tr><th scope="col">Category</th><th scope="col">Age band</th><th scope="col">Count</th></tr></thead>
          <tbody>{data.aggregates.map((row) => <tr key={`${row.category}-${row.age_band}`}><td>{statusLabel(row.category, t)}</td><td>{row.age_band}</td><td>{row.count}</td></tr>)}</tbody></table></div>
        <h2>Records</h2><div className="table-scroll"><table><thead><tr><th scope="col">Record ID</th><th scope="col">Category</th><th scope="col">Age</th><th scope="col">Gender</th><th scope="col">Pension start year</th><th scope="col">Monthly pension</th><th scope="col">Service months</th><th scope="col">Status</th></tr></thead>
          <tbody>{data.rows.map((row) => <tr key={`${row.category}-${row.record_id}`}><td>{row.record_id}</td><td>{statusLabel(row.category, t)}</td><td>{row.age_years}</td><td>{row.gender ?? "—"}</td><td>{row.pension_start_year ?? "—"}</td><td>{row.monthly_pension_paise === null ? "—" : rupees(row.monthly_pension_paise)}</td><td>{row.service_months ?? "—"}</td><td>{statusLabel(row.status, t)}</td></tr>)}</tbody></table></div>
      </> : null}
    </section> : null}
  </section>;
}
