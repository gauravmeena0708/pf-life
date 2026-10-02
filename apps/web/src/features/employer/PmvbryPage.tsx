import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import "./PmvbryPage.css";

interface Month { wage_month: string; headcount: number; eligible_employees: number; net_additional: number; eligible: boolean; slots_paid: number; incentive_paise: number }
interface Cycle { cycle_month: string; period_from: string; period_to: string; computed_paise: number; paid_paise: number; payable_paise: number; state: string; disbursal_deadline: string }
interface Plan { establishment_id: string; baseline: number; threshold: number; crossing_month: string | null; incentive_months: number; manufacturing: boolean; excluded_reason: string | null; option_exercised_at: string | null; gstin: string | null; bank_account_ref: string | null; months: Month[]; cycles: Cycle[] }

export function PmvbryPage() {
  const { t } = useTranslation(); const qc = useQueryClient(); const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const view = useQuery({ queryKey: ["employer-pmvbry"], queryFn: () => api<Envelope<Plan>>("/api/v1/employers/me/pmvbry"), retry: false });
  const p = view.data?.data;
  async function exercise(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!p || session.data?.stakeholder !== "employer.owner") return;
    const form = new FormData(event.currentTarget);
    const body = { gstin: String(form.get("gstin")).trim().toUpperCase(), bank_account_ref: String(form.get("bank_account_ref")).trim() };
    setBusy(true); setError(null); setNotice("");
    try {
      const token = await stepUp.ask({ action: "pmvbry-option", resourceId: p.establishment_id, summary: `Exercise the PMVBRY Part B option for ${p.establishment_id}.` });
      if (!token) return;
      await command("POST", "/api/v1/employers/me/pmvbry/options", body, { stepUpToken: token });
      setNotice("PMVBRY option exercised."); await qc.invalidateQueries({ queryKey: ["employer-pmvbry"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack pmvbry" aria-labelledby="employer-pmvbry-heading">
    <PageHeader id="employer-pmvbry-heading" eyebrow="Employment incentive" title="PMVBRY — support to employers (Part B)" current="PMVBRY" description="Pradhan Mantri Viksit Bharat Rozgar Yojana · Part B" />
    <p className="card">The baseline uses ECR headcount from August 2024 to July 2025. The threshold is 2 or 5 additional employees, depending on the baseline. Support is ₹1,000, ₹2,000 or ₹3,000 per eligible additional employee each month by EPF wage, for 24 months (48 in manufacturing). The first six months are paid as a lump sum; later months are paid monthly.</p>
    <ProblemMessage error={session.error} /><ProblemMessage error={view.error} /><ProblemMessage error={error} />
    {view.isLoading ? <p role="status">Loading PMVBRY record…</p> : null}{notice ? <p role="status" className="ok">{notice}</p> : null}
    {p ? <><div className="pmvbry-metrics" aria-label="Part B summary">
      {[ ["Baseline headcount", p.baseline], ["Additional employee threshold", p.threshold], ["Crossing month", p.crossing_month ?? "Not reached"], ["Incentive months", p.incentive_months], ["Manufacturing", p.manufacturing ? "Yes" : "No"] ].map(([label, value]) => <div className="card pmvbry-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}
    </div>{p.excluded_reason ? <p className="pmvbry-excluded" role="alert"><strong>Excluded:</strong> {p.excluded_reason}</p> : null}
    <section className="card stack" aria-labelledby="pmvbry-option-heading"><h2 id="pmvbry-option-heading">Employer option</h2>
      {p.option_exercised_at ? <p>Exercised on {p.option_exercised_at.slice(0, 10)} · GSTIN {p.gstin} · bank reference {p.bank_account_ref}</p>
        : session.data?.stakeholder === "employer.owner" ? <form className="stack" aria-label="Exercise PMVBRY option" onSubmit={(e) => void exercise(e)}><div className="form-row">
          <label>GSTIN<input name="gstin" required minLength={15} maxLength={15} pattern="[0-9A-Za-z]{15}" /></label>
          <label>PAN-linked bank account reference<input name="bank_account_ref" required maxLength={120} /></label></div>
          <button type="submit" className="primary" disabled={busy || !!stepUp.request}>Exercise option</button></form>
          : <p>The owner exercises the option.</p>}
    </section>
    <section className="card stack" aria-labelledby="pmvbry-months-heading"><h2 id="pmvbry-months-heading">Monthly eligibility</h2>
      {p.months.length ? <div className="table-scroll"><table><thead><tr>{["Month", "Headcount", "Eligible employees", "Net additional", "Eligible?", "Slots paid", "Incentive"].map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{p.months.map((m) => <tr key={m.wage_month}><th scope="row">{m.wage_month}</th><td>{m.headcount}</td><td>{m.eligible_employees}</td><td>{m.net_additional}</td><td>{m.eligible ? "Yes" : "No"}</td><td>{m.slots_paid}</td><td className="amount">{rupees(m.incentive_paise)}</td></tr>)}</tbody></table></div> : <p className="muted">No crossing month or eligible months recorded yet.</p>}
    </section>
    <section className="card stack" aria-labelledby="pmvbry-cycles-heading"><h2 id="pmvbry-cycles-heading">Payment cycles</h2>
      {p.cycles.length ? <div className="table-scroll"><table><thead><tr>{["Cycle month", "Period", "Computed", "Paid", "Payable", "State", "Disbursal deadline"].map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{p.cycles.map((c) => <tr key={c.cycle_month}><th scope="row">{c.cycle_month}</th><td>{c.period_from}–{c.period_to}</td><td className="amount">{rupees(c.computed_paise)}</td><td className="amount">{rupees(c.paid_paise)}</td><td className="amount">{rupees(c.payable_paise)}</td><td>{statusLabel(c.state, t)}</td><td>{c.disbursal_deadline}</td></tr>)}</tbody></table></div> : <p className="muted">No payment cycles recorded yet.</p>}
    </section></> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
