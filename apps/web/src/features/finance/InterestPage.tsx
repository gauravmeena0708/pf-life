import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { InterestRateRecord } from "./InterestRateRecord";

interface Share { due_paise: number; credited_paise: number; now_paise: number }
interface InterestPlan {
  financial_year: string;
  year_ended: boolean;
  rate_bp: number | null;
  rule_version: string;
  method: string;
  accounts: { account_link_id: string; employee: Share; employer: Share; to_credit_paise: number }[];
  total_to_credit_paise: number;
  history: { rule_version: string; rate_bp: number; revision: number; accounts: number; total_paise: number; posted_at: string }[];
}

function lastCompletedYear(): string {
  const d = new Date();
  const start = (d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1) - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

const signed = (paise: number) => paise < 0 ? `− ${rupees(-paise)}` : rupees(paise);

/** Finance (FA & CAO): annual interest crediting at the rate declared in the rule set in force. */
export function InterestPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [year, setYear] = useState(lastCompletedYear());
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const plan = useQuery({ queryKey: ["interest-plan", year], retry: false,
    queryFn: () => api<Envelope<InterestPlan>>(`/api/v1/office/accounts/interest-postings?financialYear=${encodeURIComponent(year)}`) });
  const p = plan.data?.data;
  const pending = p ? p.accounts.filter((a) => a.employee.now_paise || a.employer.now_paise) : [];
  const revision = !!p?.history.length;

  async function post() {
    if (!p || p.rate_bp === null || stepUp.request) return;
    setError(null); setNotice(null);
    const token = await stepUp.ask({ action: "post-interest", resourceId: p.financial_year, amountPaise: Math.abs(p.total_to_credit_paise),
      summary: `${revision ? "Post the revision of" : "Credit"} interest for ${p.financial_year} at ${p.rate_bp / 100}% (rule set ${p.rule_version}) to ${pending.length} accounts: ${signed(p.total_to_credit_paise)} in all.` });
    if (!token) return;
    try {
      const r = await command<Envelope<{ accounts: number; credited_paise: number; revision: boolean }>>("POST", "/api/v1/office/accounts/interest-postings",
        { financial_year: p.financial_year }, { stepUpToken: token });
      setNotice(`${r.data.revision ? "Revision posted" : "Interest credited"}: ${signed(r.data.credited_paise)} to ${r.data.accounts} accounts. Members see it in their passbooks.`);
      await qc.invalidateQueries({ queryKey: ["interest-plan", year] });
    } catch (cause) { setError(cause); }
  }

  return (
    <section className="stack" aria-labelledby="interest-heading">
      <PageHeader id="interest-heading" eyebrow="Finance and accounts" title="Annual interest crediting"
        description="Interest is credited once a financial year has ended, at the rate declared for that year in the rule set in force. A revised rate credits only the difference." current="Interest" />
      <form className="card search-input-row" onSubmit={(e) => { e.preventDefault(); const v = String(new FormData(e.currentTarget).get("fy")); if (/^\d{4}-\d{2}$/.test(v)) setYear(v); }}>
        <label>Financial year<input name="fy" defaultValue={year} pattern="\d{4}-\d{2}" placeholder="2025-26" /></label>
        <button type="submit">Show</button>
      </form>
      <ProblemMessage error={plan.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {p ? (
        <>
          <section className="card stack" aria-labelledby="rate-heading"><h2 id="rate-heading">Rate for {p.financial_year}</h2>
            {p.rate_bp === null ? <p className="problem">No rate is declared for {p.financial_year} in the rule set in force ({p.rule_version}). The policy drafter adds it under Interest on PF accounts.</p>
              : <p><strong className="figure">{p.rate_bp / 100}%</strong> <span className="muted">from rule set {p.rule_version}</span></p>}
            <p className="muted small">{p.method}</p>
            {!p.year_ended ? <p className="demo-tip">{p.financial_year} has not ended yet; interest is credited after 31 March.</p> : null}
          </section>

          {p.rate_bp !== null ? (
            <section className="card stack" aria-labelledby="accounts-heading"><h2 id="accounts-heading">Accounts</h2>
              <div className="table-scroll"><table>
                <thead><tr><th scope="col">Account</th><th scope="col">Due at {p.rate_bp / 100}% (employee + employer)</th><th scope="col">Already credited</th><th scope="col">To credit now</th></tr></thead>
                <tbody>{p.accounts.map((a) => (
                  <tr key={a.account_link_id}><td>{a.account_link_id}</td>
                    <td>{rupees(a.employee.due_paise)} + {rupees(a.employer.due_paise)}</td>
                    <td>{rupees(a.employee.credited_paise + a.employer.credited_paise)}</td>
                    <td><strong>{signed(a.to_credit_paise)}</strong></td></tr>
                ))}</tbody>
                <tfoot><tr><th scope="row" colSpan={3}>Total</th><td><strong>{signed(p.total_to_credit_paise)}</strong></td></tr></tfoot>
              </table></div>
              <div className="actions">
                <button type="button" className="primary" disabled={!p.year_ended || pending.length === 0 || !!stepUp.request} onClick={() => void post()}>
                  {revision ? "Post the revision" : "Credit interest"}</button>
                {pending.length === 0 ? <span className="muted small">Every account is credited at this rate.</span> : null}
              </div>
            </section>
          ) : null}

          <section className="card stack" aria-labelledby="runs-heading"><h2 id="runs-heading">Runs for {p.financial_year}</h2>
            {p.history.length === 0 ? <p className="muted">No interest credited for this year yet.</p> : (
              <div className="table-scroll"><table>
                <thead><tr><th scope="col">Posted</th><th scope="col">Rule set</th><th scope="col">Rate</th><th scope="col">Kind</th><th scope="col">Accounts</th><th scope="col">Amount</th></tr></thead>
                <tbody>{p.history.map((h) => (
                  <tr key={`${h.rule_version}-${h.revision}`}><td>{new Date(h.posted_at).toLocaleString("en-IN")}</td><td>{h.rule_version}</td><td>{h.rate_bp / 100}%</td>
                    <td>{h.revision ? "Revision (difference)" : "First credit"}</td><td>{h.accounts}</td><td>{signed(h.total_paise)}</td></tr>
                ))}</tbody>
              </table></div>)}
          </section>
        </>
      ) : null}
      <InterestRateRecord defaultYear={year} stepUp={stepUp} />
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
