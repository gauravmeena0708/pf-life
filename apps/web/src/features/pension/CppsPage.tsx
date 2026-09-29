import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface DisbursementRun {
  run_id: string;
  month: string;
  state: string;
  pensions: number;
  total_paise: number;
  paid_total_paise: number | null;
  exceptions: { ppo_id: string | null; amount_paise: number; reason: string }[];
  lines: { ppo_id: string; amount_paise: number; status: string }[];
}

interface Brs {
  brs_id: string;
  month: string;
  scroll_total_paise: number;
  bank_debit_total_paise: number;
  difference_paise: number;
  unreconciled: { ppo_id: string; amount_paise: number; status: string }[];
}

function label(value: string) {
  return value.replace(/_/g, " ").toLowerCase();
}

export function CppsPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [brs, setBrs] = useState<Brs | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  const runs = useQuery({
    queryKey: ["cpps", "disbursement-runs"],
    queryFn: () => api<Envelope<DisbursementRun[]>>("/api/v1/cpps/disbursement-runs"),
    retry: false,
  });

  async function startRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const month = String(new FormData(element).get("month") ?? "");
    if (!month) return;
    setError(null);
    setNotice(null);
    setBusy("run");
    try {
      const token = await stepUp.ask({ action: "run-disbursement", resourceId: month, summary: `Create and send the pension disbursement run for ${month}.` });
      if (!token) return;
      await command("POST", "/api/v1/cpps/disbursement-runs", { month }, { stepUpToken: token });
      setNotice(`Disbursement run created for ${month}.`);
      element.reset();
      await qc.invalidateQueries({ queryKey: ["cpps", "disbursement-runs"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(null);
    }
  }

  async function reconcile(run: DisbursementRun) {
    setError(null);
    setNotice(null);
    setBusy(run.run_id);
    try {
      const token = await stepUp.ask({ action: "reconcile-disbursement", resourceId: run.run_id,
        summary: `Reconcile the pension disbursement run ${run.run_id} for ${run.month}.` });
      if (!token) return;
      await command("POST", "/api/v1/cpps/reconciliations", { run_id: run.run_id }, { stepUpToken: token });
      setNotice(`Disbursement run ${run.run_id} reconciled.`);
      await qc.invalidateQueries({ queryKey: ["cpps", "disbursement-runs"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(null);
    }
  }

  async function prepareBrs(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const month = String(new FormData(event.currentTarget).get("month") ?? "");
    if (!month) return;
    setError(null);
    setNotice(null);
    setBrs(null);
    setBusy("brs");
    try {
      const token = await stepUp.ask({ action: "prepare-brs", resourceId: month,
        summary: `Prepare the Bank Reconciliation Statement for ${month}.` });
      if (!token) return;
      const result = await command<Envelope<Brs>>("POST", "/api/v1/office/pensions/brs-reconciliations", { month }, { stepUpToken: token });
      setBrs(result.data);
      setNotice(`Bank Reconciliation Statement ${result.data.brs_id} prepared.`);
      await qc.invalidateQueries({ queryKey: ["cpps", "disbursement-runs"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(null);
    }
  }

  return <div className="stack">
    <PageHeader id="cpps-page-heading" eyebrow="Centralised Pension Payment System" title="CPPS disbursement"
      description="Review monthly pension disbursement and bank reconciliation." current="CPPS" />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    <ProblemMessage error={error} />
    <ProblemMessage error={session.error} />
    <section className="card stack" aria-labelledby="runs-heading">
      <h2 id="runs-heading">Monthly disbursement runs</h2>
      {role === "tech.cpps" ? <form className="stack" onSubmit={(event) => void startRun(event)}>
        <div className="form-row"><label>Month<input name="month" type="month" required /></label></div>
        <div className="actions"><button type="submit" className="primary" disabled={busy !== null}>Run disbursement</button></div>
      </form> : null}
      <ProblemMessage error={runs.error} />
      {runs.isLoading ? <p role="status">Loading disbursement runs…</p> : null}
      {runs.data?.data.length === 0 ? <p className="muted small">No disbursement runs.</p> : null}
      {runs.data?.data.length ? <div className="table-scroll"><table>
        <thead><tr><th scope="col">Month</th><th scope="col">State</th><th scope="col">Pensions</th>
          <th scope="col">Total</th><th scope="col">Paid total</th><th scope="col">Exceptions</th>
          {role === "tech.cpps" ? <th scope="col">Action</th> : null}</tr></thead>
        <tbody>{runs.data.data.map((run) => <tr key={run.run_id}>
          <td>{run.month}</td>
          <td><span className="state-pill">{label(run.state)}</span></td>
          <td>{run.pensions}</td>
          <td>{rupees(run.total_paise)}</td>
          <td>{rupees(run.paid_total_paise)}</td>
          <td>{run.exceptions.length}<details><summary>View exceptions</summary>
            {run.exceptions.length ? <ul>{run.exceptions.map((item, index) => <li key={`${item.ppo_id ?? "total"}-${index}`}>
              {item.ppo_id ? `PPO ${item.ppo_id}: ` : "Run total: "}{rupees(item.amount_paise)} — {item.reason}
            </li>)}</ul> : <p className="muted small">No exceptions.</p>}
          </details></td>
          {role === "tech.cpps" ? <td>{run.state === "SENT" || run.state === "STATEMENT_RECEIVED"
            ? <button type="button" className="primary" disabled={busy !== null} onClick={() => void reconcile(run)}>Reconcile</button>
            : null}</td> : null}
        </tr>)}</tbody>
      </table></div> : null}
    </section>
    {role === "fo.apfc_pension" ? <section className="card stack" aria-labelledby="brs-heading">
      <h2 id="brs-heading">Bank Reconciliation Statement</h2>
      <form className="stack" onSubmit={(event) => void prepareBrs(event)}>
        <div className="form-row"><label>Month<input name="month" type="month" required /></label></div>
        <div className="actions"><button type="submit" className="primary" disabled={busy !== null}>Prepare statement</button></div>
      </form>
      {brs ? <div className="stack">
        <dl className="kv">
          <div><dt>Statement</dt><dd>{brs.brs_id}</dd></div>
          <div><dt>Month</dt><dd>{brs.month}</dd></div>
          <div><dt>Scroll total</dt><dd>{rupees(brs.scroll_total_paise)}</dd></div>
          <div><dt>Bank debit total</dt><dd>{rupees(brs.bank_debit_total_paise)}</dd></div>
          <div><dt>Difference</dt><dd>{rupees(brs.difference_paise)}</dd></div>
        </dl>
        <h3>Unreconciled payments</h3>
        <div className="table-scroll"><table>
          <thead><tr><th scope="col">PPO</th><th scope="col">Amount</th><th scope="col">Status</th></tr></thead>
          <tbody>{brs.unreconciled.map((item, index) => <tr key={`${item.ppo_id}-${index}`}>
            <td>{item.ppo_id}</td><td>{rupees(item.amount_paise)}</td><td><span className="state-pill">{label(item.status)}</span></td>
          </tr>)}{brs.unreconciled.length === 0 ? <tr><td colSpan={3}>No unreconciled payments.</td></tr> : null}</tbody>
        </table></div>
      </div> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </div>;
}
