import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import "./Form16A.css";

interface Quarter { quarter: string; amount_paid_paise: number; tds_paise: number }
interface Certificate { certificate_no: string; financial_year: string; section: string; note: string;
  deductor: { name: string; tan: string; office_id: string | null }; deductee: { name: string | null; pan_masked: string | null; pan_status: string };
  quarters: Quarter[]; totals: { amount_paid_paise: number; tds_paise: number } }

const year = new Date().getFullYear() - (new Date().getMonth() < 3 ? 1 : 0);
const years = [year, year - 1, year - 2].map((start) => `${start}-${String(start + 1).slice(-2)}`);

export function Form16A() {
  const { t } = useTranslation();
  const [fy, setFy] = useState(years[0]);
  const certificate = useQuery({ queryKey: ["form-16a", fy], queryFn: () => api<Envelope<Certificate>>(`/api/v1/members/me/tax/form-16a?financialYear=${fy}`), retry: false });
  const data = certificate.data?.data;
  return <section className="card stack form-16a" aria-labelledby="form-16a-heading">
    <h2 id="form-16a-heading">TDS certificate (Form 16A)</h2>
    <label>Financial year<select value={fy} onChange={(e) => setFy(e.target.value)}>{years.map((value) => <option key={value}>{value}</option>)}</select></label>
    <ProblemMessage error={certificate.error} />
    {data ? <>
      <p><strong>Certificate number:</strong> {data.certificate_no} · <strong>Section:</strong> {data.section}</p>
      <div className="form-16a-parties"><div><h3>Deductor</h3><p>{data.deductor.name}<br />TAN: {data.deductor.tan}<br />Office: {data.deductor.office_id ?? "—"}</p></div>
        <div><h3>Deductee</h3><p>{data.deductee.name ?? "—"}<br />PAN: {data.deductee.pan_masked ?? "—"}<br />PAN status: {statusLabel(data.deductee.pan_status, t)}</p></div></div>
      <div className="table-scroll"><table><thead><tr><th scope="col">Quarter</th><th scope="col" className="numeric">Amount paid</th><th scope="col" className="numeric">TDS</th></tr></thead>
        <tbody>{data.quarters.map((q) => <tr key={q.quarter}><th scope="row">{q.quarter}</th><td className="numeric">{rupees(q.amount_paid_paise)}</td><td className="numeric">{rupees(q.tds_paise)}</td></tr>)}</tbody>
        <tfoot><tr><th scope="row">Total</th><td className="numeric">{rupees(data.totals.amount_paid_paise)}</td><td className="numeric">{rupees(data.totals.tds_paise)}</td></tr></tfoot></table></div>
      <p className="muted small">{data.note}</p><div className="actions form-16a-print"><button type="button" onClick={() => window.print()}>Print</button></div>
    </> : certificate.isLoading ? <p role="status">Loading certificate…</p> : null}
  </section>;
}
