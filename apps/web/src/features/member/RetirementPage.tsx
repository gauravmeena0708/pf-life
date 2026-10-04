import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { pensionAt58, retirementRows, type PensionEstimate, type PfForecast } from "./retirement";

/** P2.23: one view of retirement — PF and pension at 58, the income against the final wages, and what VPF would add. */
export function RetirementPage() {
  const [vpf, setVpf] = useState(0);
  const [draft, setDraft] = useState("10");
  const pf = useQuery({ queryKey: ["retirement-forecast", vpf], retry: false,
    queryFn: () => api<Envelope<PfForecast>>(`/api/v1/members/me/retirement-forecast?vpf_pct=${vpf}`) });
  const pension = useQuery({ queryKey: ["pension-estimate"], retry: false,
    queryFn: () => api<Envelope<PensionEstimate>>("/api/v1/members/me/pension-eligibility-preview") });
  const f = pf.data?.data;
  const p = pension.data?.data;
  const rows = f ? retirementRows(f, p) : [];
  const at58 = f ? pensionAt58(f, p) : undefined;
  const submit = (e: FormEvent) => { e.preventDefault(); setVpf(Math.max(0, Number(draft) || 0)); };
  const maxPct = f ? f.assumptions.vpf_max_bp / 100 : 88;

  return (
    <section className="stack" aria-labelledby="retirement-heading">
      <PageHeader id="retirement-heading" eyebrow="Member services" title="Retirement view" current="Retirement view"
        description="Your Provident Fund and pension at 58 in one place: what they would give you a month, against your wages then." />
      <ProblemMessage error={pf.error} />
      {f ? <>
        <section className="card stack" aria-labelledby="retirement-today-heading"><h2 id="retirement-today-heading">Where you are today</h2>
          <dl className="kv">
            <dt>PF balance (all your member IDs)</dt><dd>{rupees(f.balance_now_paise)}</dd>
            <dt>Wages (latest contribution)</dt><dd>{f.in_service ? rupees(f.wages_now_paise) : "Not in service — no contributions to come"}</dd>
            <dt>Retirement (age 58)</dt><dd>{f.retire_on}{f.months_to_go ? ` — ${Math.floor(f.months_to_go / 12)} years ${f.months_to_go % 12} months to go` : ""}</dd>
          </dl>
        </section>
        <section className="card stack" aria-labelledby="retirement-forecast-heading"><h2 id="retirement-forecast-heading">At 58</h2>
          <div className="table-scroll"><table>
            <thead><tr><th scope="col">If you save</th><th scope="col">PF at 58</th><th scope="col">PF as an income</th><th scope="col">Pension</th>
              <th scope="col">A month in all</th><th scope="col">Of your wages then</th></tr></thead>
            <tbody>{rows.map((r) => <tr key={r.vpfPct}>
              <th scope="row">{r.vpfPct ? `12% + ${r.vpfPct}% VPF` : "12% (as now)"}{r.vpfNow ? <div className="muted small">VPF costs {rupees(r.vpfNow)} a month now</div> : null}</th>
              <td>{rupees(r.corpus)}</td><td>{rupees(r.pfIncome)}</td><td>{r.pension ? rupees(r.pension) : "—"}</td>
              <td><strong>{rupees(r.total)}</strong></td><td>{r.replacementPct === null ? "—" : `${r.replacementPct}%`}</td></tr>)}</tbody>
          </table></div>
          {at58 && !at58.eligible ? <p className="pending-notice">No monthly pension at 58 yet: {at58.reason}</p> : null}
          {at58?.eligible ? <p className="muted small">Pension: {at58.working}.</p> : null}
          {rows.some((r) => r.taxableYears) ? <p className="pending-notice">With VPF, your own contributions go above {rupees(f.assumptions.taxable_interest_threshold_paise ?? 0)} a
            year in {Math.max(...rows.map((r) => r.taxableYears))} of the years: the interest on the part above it is taxable.</p> : null}
          {f.in_service ? <form className="search-input-row" onSubmit={submit} aria-label="VPF what-if">
            <label>Voluntary PF (VPF), % of wages<input type="number" min={0} max={maxPct} step={1} value={draft} onChange={(e) => setDraft(e.target.value)} /></label>
            <button type="submit">Show with VPF</button></form> : null}
        </section>
        <p className="muted small">Assumptions: interest at {f.assumptions.interest_rate_bp / 100}% a year (declared for {f.assumptions.interest_declared_for ?? "—"}),
          wages rising {f.assumptions.wage_growth_bp / 100}% a year, the PF read as an income of {f.assumptions.drawdown_rate_bp / 100}% of it a year.
          {" "}{f.note} ({f.assumptions.rule_version})</p>
      </> : pf.isLoading ? <p role="status">Working it out…</p> : null}
    </section>
  );
}
