import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, command, getSession, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import "./PmvbryDashboard.css";

interface Payment { kind: "A" | "B"; beneficiary: string; instalment: number | null; cycle_month: string | null; amount_paise: number; state: string }
interface Preview { as_of_month: string; dry_run: true; amount_paise: number; held_paise: number; payments: Payment[] }
interface Result { run_id: string; as_of_month: string; part_a_paise: number; part_b_paise: number; held_paise: number; payments: Payment[] }
interface Dashboard { part_a_beneficiaries: number; part_b_establishments: number; states: Record<string, number>; due_age_buckets: Record<string, number>; by_industry_group: Record<string, { part_a_beneficiaries: number; part_b_establishments: number; paid_paise: number; held_paise: number; due_paise: number }>; excluded_establishments: { establishment_id: string; reason: string }[] }
/** The latest month whose ECRs can be in: last month. */
const currentMonth = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
export function PmvbryDashboard() {
  const { t } = useTranslation(); const qc = useQueryClient(); const stepUp = useStepUp();
  const paymentKey = useRef<string | null>(null);
  const [month, setMonth] = useState(currentMonth); const [preview, setPreview] = useState<Preview | null>(null); const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<unknown>(null); const [busy, setBusy] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const view = useQuery({ queryKey: ["ho-pmvbry"], queryFn: () => api<Envelope<Dashboard>>("/api/v1/ho/pmvbry/dashboard"), retry: false });
  const d = view.data?.data;
  async function showPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); paymentKey.current = null; setError(null); setResult(null); setPreview(null); setBusy(true);
    try { const r = await api<Envelope<Preview>>(`/api/v1/ho/pmvbry/disbursement-runs/preview?as_of_month=${encodeURIComponent(month)}`); setPreview(r.data); }
    catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  async function pay() {
    if (!preview || busy || stepUp.request) return;
    setError(null); setBusy(true);
    try { const token = await stepUp.ask({ action: "pmvbry-disbursement", resourceId: preview.as_of_month, amountPaise: preview.amount_paise, summary: `Pay PMVBRY disbursements for ${preview.as_of_month}: ${rupees(preview.amount_paise)}.` });
      if (!token) return;
      const r = await command<Envelope<Result>>("POST", "/api/v1/ho/pmvbry/disbursement-runs", { as_of_month: preview.as_of_month }, { stepUpToken: token, idempotencyKey: paymentKey.current ??= newIdempotencyKey() });
      paymentKey.current = null; setResult(r.data); setPreview(null); await qc.invalidateQueries({ queryKey: ["ho-pmvbry"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack pmvbry" aria-labelledby="ho-pmvbry-heading">
    <PageHeader id="ho-pmvbry-heading" eyebrow="Head office · employment incentive" title="PMVBRY dashboard" current="PMVBRY" description="Part A and Part B beneficiaries, payment states and disbursement oversight." />
    <ProblemMessage error={session.error} /><ProblemMessage error={view.error} /><ProblemMessage error={error} />{view.isLoading ? <p role="status">Loading PMVBRY dashboard…</p> : null}
    {d ? <><div className="pmvbry-metrics" aria-label="PMVBRY totals">{[["Part A beneficiaries", d.part_a_beneficiaries], ["Part B establishments", d.part_b_establishments], ["Paid", d.states.PAID ?? 0], ["Held", d.states.HELD ?? 0], ["Due", d.states.DUE ?? 0], ["Excluded establishments", d.excluded_establishments.length]].map(([label, value]) => <div className="card pmvbry-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <section className="card stack" aria-labelledby="pmvbry-age-heading"><h2 id="pmvbry-age-heading">Due by age</h2><div className="pmvbry-age">{Object.entries(d.due_age_buckets).map(([age, count]) => <p key={age}><strong>{count}</strong><span>{age} days</span></p>)}</div></section>
      <section className="card stack" aria-labelledby="pmvbry-industry-heading"><h2 id="pmvbry-industry-heading">By industry</h2><div className="table-scroll"><table><thead><tr>{["Industry", "Part A beneficiaries", "Part B establishments", "Paid", "Held", "Due"].map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{Object.entries(d.by_industry_group).map(([group, row]) => <tr key={group}><th scope="row">{group === "manufacturing" ? "Manufacturing" : "Other"}</th><td>{row.part_a_beneficiaries}</td><td>{row.part_b_establishments}</td><td>{rupees(row.paid_paise)}</td><td>{rupees(row.held_paise)}</td><td>{rupees(row.due_paise)}</td></tr>)}</tbody></table></div>{!Object.keys(d.by_industry_group).length ? <p>No industry entries yet.</p> : null}</section>
      <section className="card stack" aria-labelledby="pmvbry-excluded-heading"><h2 id="pmvbry-excluded-heading">Excluded establishments</h2>{d.excluded_establishments.length ? <ul>{d.excluded_establishments.map((item) => <li key={item.establishment_id}><strong>{item.establishment_id}</strong>: {item.reason}</li>)}</ul> : <p>None recorded.</p>}</section></> : null}
    {session.data?.stakeholder === "ho.fa_cao" ? <section className="card stack" aria-labelledby="pmvbry-run-heading"><h2 id="pmvbry-run-heading">Disbursement run</h2>
      <form className="form-row" onSubmit={(e) => void showPreview(e)}><label>As of month<input type="month" required value={month} onChange={(e) => { paymentKey.current = null; setMonth(e.target.value); setPreview(null); setResult(null); }} /></label><button type="submit" disabled={busy}>Preview</button></form>
      {preview ? <div className="stack" aria-label="Disbursement preview"><h3>Preview for {preview.as_of_month}</h3><p>Payable: <strong>{rupees(preview.amount_paise)}</strong> · Held: {rupees(preview.held_paise)}</p>
        <PaymentTable payments={preview.payments} t={t} /><button className="primary" type="button" disabled={busy} onClick={() => void pay()}>Pay {rupees(preview.amount_paise)}</button></div> : null}
      {result ? <div role="status" className="stack"><h3>Run {result.run_id} completed</h3><p>Part A: {rupees(result.part_a_paise)} · Part B: {rupees(result.part_b_paise)} · Held: {rupees(result.held_paise)}</p><PaymentTable payments={result.payments} t={t} /></div> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
function PaymentTable({ payments, t }: { payments: Payment[]; t: ReturnType<typeof useTranslation>["t"] }) {
  return payments.length ? <div className="table-scroll"><table><thead><tr>{["Kind", "Beneficiary", "Instalment / cycle", "Amount", "State"].map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{payments.map((p, i) => <tr key={`${p.kind}-${p.beneficiary}-${p.instalment ?? p.cycle_month}-${i}`}><th scope="row">Part {p.kind}</th><td>{p.beneficiary}</td><td>{p.instalment ? `Instalment ${p.instalment}` : p.cycle_month}</td><td>{rupees(p.amount_paise)}</td><td>{statusLabel(p.state, t)}</td></tr>)}</tbody></table></div> : <p>No payments in this run.</p>;
}
