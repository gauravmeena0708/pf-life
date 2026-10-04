import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Month { wage_month: string; basis: string; amount_paise: number; rate_bp: number; months: number; interest_paise: number }
export interface Rectification { rectification_id: string; account_link_id: string; uan: string; scenario: "WRONGLY_ALLOWED" | "WRONGLY_DENIED";
  scenario_label: string; exempted_trust: string | null; from_month: string; to_month: string; total_paise: number; notesheet_no: string;
  remarks: string; state: string; decision_note: string | null; journal_id: string | null; trust_reference: string | null; circular: string;
  worksheet: { months: Month[]; amount_paise: number; interest_paise: number; total_paise: number; worked_out_on: string } }

const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();

/** P2.19c: rectifying erroneous EPS contributions (HO circular WSU/2025/E-961539, 19 Dec 2025). The DA (Accounts) works it
 *  out from the posted returns, the APFC approves, Cash records an exempted trust's remittance. */
export function EpsRectificationSection({ role }: { role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["eps-rectifications"], retry: false, queryFn: () => api<Envelope<Rectification[]>>("/api/v1/office/eps-rectifications") });
  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try { const done = await work(); if (done) setNotice(done); await qc.invalidateQueries({ queryKey: ["eps-rectifications"] }); } catch (cause) { setError(cause); }
  }
  const propose = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const account = text(f, "account");
    void run(async () => {
      const token = await stepUp.ask({ action: "propose-eps-rectification", resourceId: account, summary: `Propose the EPS rectification of ${account}.` });
      if (!token) return null;
      const r = await command<Envelope<Rectification>>("POST", "/api/v1/office/eps-rectifications", { account_link_id: account, scenario: text(f, "scenario"),
        from_month: text(f, "from"), to_month: text(f, "to"), notesheet_no: text(f, "notesheet"), remarks: text(f, "remarks"),
        trust_rate_bp: text(f, "trust_rate") ? Math.round(Number(text(f, "trust_rate")) * 100) : null }, { stepUpToken: token });
      form.reset();
      return `${r.data.rectification_id}: ${rupees(r.data.total_paise)} worked out — sent to the APFC.`;
    }); };
  const decide = (r: Rectification, decision: "APPROVE" | "REJECT") => void run(async () => {
    const token = await stepUp.ask({ action: "approve-eps-rectification", resourceId: r.rectification_id, amountPaise: r.total_paise,
      summary: `${decision === "APPROVE" ? "Approve" : "Reject"} ${r.rectification_id}: ${rupees(r.total_paise)}.` });
    if (!token) return null;
    await command("POST", `/api/v1/office/eps-rectifications/${r.rectification_id}/approvals`,
      { decision, note: decision === "APPROVE" ? "Worked out from the posted returns; in order" : "Not in order" }, { stepUpToken: token });
    return `${r.rectification_id} ${decision === "APPROVE" ? "approved" : "rejected"}.`;
  });
  const remit = (e: FormEvent<HTMLFormElement>, r: Rectification) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    void run(async () => {
      await command("POST", `/api/v1/office/eps-rectifications/${r.rectification_id}/trust-remittances`, { reference: text(f, "reference"), amount_paise: r.total_paise });
      return `${r.rectification_id}: the trust's remittance recorded; the pension service is credited.`;
    }); };
  const rows = list.data?.data ?? [];
  return (
    <section className="card stack" aria-labelledby="eps-rect-heading"><h2 id="eps-rect-heading">EPS rectification</h2>
      <p className="muted small">Pension (EPS) contributions remitted for a member not eligible, or not remitted for one who is — rectified as HO circular
        WSU/2025/E-961539 (19 Dec 2025) sets out: worked out month by month from the posted returns with interest at the declared rate, moved between
        A/c 1 and A/c 10 (or the trust), and the pension service deleted or credited.</p>
      <ProblemMessage error={error ?? list.error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {role === "fo.da_accounts" ? <form className="stack" aria-label="Work out an EPS rectification" onSubmit={propose}>
        <div className="form-row">
          <label>Member ID<input name="account" required placeholder="AL-…" /></label>
          <label>Scenario<select name="scenario"><option value="WRONGLY_ALLOWED">I — EPS allowed to a member not eligible</option>
            <option value="WRONGLY_DENIED">II — EPS denied to an eligible member</option></select></label>
          <label>From (wage month)<input name="from" type="month" required /></label><label>To<input name="to" type="month" required /></label>
        </div>
        <div className="form-row">
          <label>Notesheet no.<input name="notesheet" required minLength={3} /></label>
          <label>Trust's declared rate, % (scenario II, exempted only)<input name="trust_rate" type="number" min={0} max={20} step="0.01" /></label>
        </div>
        <label>Remarks (why: e.g. joined after 1 Sep 2014 on wages above the ceiling)<textarea name="remarks" required minLength={10} /></label>
        <div className="actions"><button type="submit" className="primary">Work out and propose</button></div>
      </form> : null}
      {rows.length ? rows.map((r) => <article key={r.rectification_id} className="stack" aria-label={r.rectification_id}>
        <h3>{r.rectification_id} · {r.account_link_id} <span className="state-pill">{statusLabel(r.state, t)}</span></h3>
        <p>{r.scenario_label}{r.exempted_trust ? ` — PF with ${r.exempted_trust}` : ""}. {r.from_month} to {r.to_month}. Notesheet {r.notesheet_no}: {r.remarks}</p>
        <div className="table-scroll"><table aria-label={`Working of ${r.rectification_id}`}>
          <thead><tr><th scope="col">Wage month</th><th scope="col">Basis</th><th scope="col">Amount</th><th scope="col">Interest</th></tr></thead>
          <tbody>{r.worksheet.months.map((m) => <tr key={m.wage_month}><td>{m.wage_month}</td><td>{m.basis}</td><td>{rupees(m.amount_paise)}</td>
            <td>{rupees(m.interest_paise)} <span className="muted small">({m.rate_bp / 100}% for {m.months} months)</span></td></tr>)}</tbody>
          <tfoot><tr><th scope="row" colSpan={2}>Total {r.scenario === "WRONGLY_ALLOWED" ? (r.exempted_trust ? "A/c 10 → trust" : "A/c 10 → A/c 1") : (r.exempted_trust ? "trust → A/c 10" : "A/c 1 → A/c 10")}</th>
            <td>{rupees(r.worksheet.amount_paise)}</td><td><strong>{rupees(r.total_paise)}</strong> with interest</td></tr></tfoot>
        </table></div>
        {r.state === "PROPOSED" && role === "fo.apfc" ? <div className="actions"><button type="button" className="primary" onClick={() => decide(r, "APPROVE")}>Approve</button>
          <button type="button" onClick={() => decide(r, "REJECT")}>Reject</button></div> : null}
        {r.state === "AWAITING_TRUST_REMITTANCE" && role === "fo.cash" ? <form className="search-input-row" onSubmit={(e) => remit(e, r)}>
          <label>Trust's remittance reference<input name="reference" required minLength={4} /></label><button type="submit">Record {rupees(r.total_paise)}</button></form> : null}
      </article>) : list.isSuccess ? <p className="muted">No rectifications yet.</p> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
