import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { command, getSession, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import type { useStepUp } from "../stepup/useStepUp";

interface RateRecord {
  declaration_id: string; financial_year: string; rate_bp: number; next_step: string;
  recorded: { declaration_id: string; rate_bp: number; ministry_concurrence_ref: string; created_at: string }[];
}

export function InterestRateRecord({ defaultYear, stepUp }: { defaultYear: string; stepUp: ReturnType<typeof useStepUp> }) {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const finance = session.data?.stakeholder === "ho.fa_cao";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<RateRecord | null>(null);

  async function record(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!finance || busy) return;
    const f = new FormData(e.currentTarget);
    const financialYear = String(f.get("financial_year") ?? "").trim();
    const percent = String(f.get("percent") ?? "").trim();
    const body = { rate_bp: Math.round(Number(percent) * 100), cbt_recommended_on: String(f.get("cbt_recommended_on") ?? ""),
      ministry_concurrence_ref: String(f.get("ministry_concurrence_ref") ?? "").trim(),
      ministry_concurrence_on: String(f.get("ministry_concurrence_on") ?? ""), note: String(f.get("note") ?? "").trim() };
    setBusy(true); setError(null); setResult(null);
    try {
      const fy = /^(\d{4})-(\d{2})$/.exec(financialYear);
      if (!fy || (Number(fy[1]) + 1) % 100 !== Number(fy[2])) throw new Error("Write a consecutive financial year as 2025-26.");
      if (!/^\d+(\.\d{1,2})?$/.test(percent) || !Number.isSafeInteger(body.rate_bp) || body.rate_bp < 0 || body.rate_bp > 2000) {
        throw new Error("Enter a rate from 0 to 20 percent, with at most two decimal places.");
      }
      if (!body.cbt_recommended_on || !body.ministry_concurrence_on || body.ministry_concurrence_ref.length < 3
        || body.ministry_concurrence_on < body.cbt_recommended_on) throw new Error("Enter the CBT recommendation and subsequent Ministry concurrence details.");
      const token = await stepUp.ask({ action: "record-interest-rate", resourceId: financialYear, amountPaise: body.rate_bp,
        summary: `Record the interest rate for ${financialYear} at ${(body.rate_bp / 100).toFixed(2)}% with Ministry concurrence ${body.ministry_concurrence_ref}.` });
      if (!token) return;
      setResult((await command<Envelope<RateRecord>>("PUT", `/api/v1/ho/config/interest-rates/${encodeURIComponent(financialYear)}`, body, { stepUpToken: token })).data);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <section className="card stack" aria-labelledby="interest-rate-record-heading">
    <h2 id="interest-rate-record-heading">Record the interest rate</h2>
    <ProblemMessage error={error ?? session.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !finance ? <p className="pending-notice">Interest rates are recorded by HO Finance and Accounts.</p> : null}
    {finance ? <>
      <form className="stack" aria-labelledby="interest-rate-record-heading" onSubmit={(e) => void record(e)}>
        <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>Approved rate and concurrence</legend>
          <div className="form-row">
            <label>Financial year to record<input name="financial_year" required defaultValue={defaultYear} pattern="[0-9]{4}-[0-9]{2}" /></label>
            <label>Rate (%)<input name="percent" type="number" min="0" max="20" step="0.01" required placeholder="8.25" /></label>
            <label>CBT recommended on<input name="cbt_recommended_on" type="date" required /></label>
            <label>Ministry concurrence reference<input name="ministry_concurrence_ref" required minLength={3} maxLength={80} /></label>
            <label>Ministry concurred on<input name="ministry_concurrence_on" type="date" required /></label>
          </div>
          <label>Note (optional)<textarea name="note" maxLength={1000} /></label>
          <div className="actions"><button type="submit" className="primary">Record interest rate</button></div>
        </fieldset>
      </form>
      {result ? <div className="stack" role="status"><p>{result.next_step}</p>
        <h3>Recorded rates for {result.financial_year}</h3>
        <div className="table-scroll"><table><thead><tr><th scope="col">Record</th><th scope="col">Rate</th><th scope="col">Ministry reference</th><th scope="col">Recorded on</th></tr></thead>
          <tbody>{result.recorded.map((row) => <tr key={row.declaration_id}><th scope="row">{row.declaration_id}</th><td>{(row.rate_bp / 100).toFixed(2)}%</td>
            <td>{row.ministry_concurrence_ref}</td><td>{row.created_at}</td></tr>)}</tbody></table></div>
      </div> : null}
    </> : null}
  </section>;
}
