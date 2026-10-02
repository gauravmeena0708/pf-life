import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const base = "/api/v1/office/exempted";
interface Reco { reco_id: string; statement_total_paise: number; receipts: { component: string; reference: string; amount_paise: number }[];
  receipts_paise: number; state: string; summary: { outstanding_after_paise: number; statement_difference_paise: number } }
interface Position { establishment_id: string; legal_name: string; credited_paise: number; received_paise: number; outstanding_paise: number;
  unreconciled_receipts: { vdr_id: string; instrument: string; instrument_ref: string; amount_paise: number; received_on: string }[];
  reconciliations: Reco[] }
const STATE: Record<string, string> = { PROPOSED: "Awaiting the APFC", RECONCILED: "Reconciled", SHORT: "Received — still short", REJECTED: "Rejected" };

/** PAST ACCUM VDR RECO: a de-exempted trust's past accumulations — the demand draft (VDR), the SDS balance and the
 *  securities (HO's reference) — matched with the members credited and the Form SE-6 statement. DA (Accounts) proposes;
 *  the APFC approves. */
export function PastAccumulationReco({ role }: { role: string }) {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const data = useQuery({ queryKey: ["office-pa-reco"], retry: false, queryFn: () => api<Envelope<Position[]>>(`${base}/past-accumulation-vdr-reconciliations`) });
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toPaise = (v: FormDataEntryValue | null) => Math.round(Number(v || 0) * 100);

  async function run(work: () => Promise<string>) {
    setBusy(true); setError(null); setNotice(null);
    try { setNotice(await work()); await qc.invalidateQueries({ queryKey: ["office-pa-reco"] }); } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  function propose(e: FormEvent<HTMLFormElement>, p: Position) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    const receipts: Record<string, unknown>[] = f.getAll("vdr").map((v) => ({ component: "CASH", vdr_id: String(v) }));
    for (const c of ["SDS", "SECURITIES"]) {
      if (f.get(`${c}_ref`)) receipts.push({ component: c, ho_reference: String(f.get(`${c}_ref`)), amount_paise: toPaise(f.get(`${c}_amount`)) });
    }
    void run(async () => {
      const r = await command<Envelope<Reco>>("POST", `${base}/${p.establishment_id}/past-accumulation-vdr-reconciliations`,
        { statement_total_paise: toPaise(f.get("statement")), receipts, note: String(f.get("note") ?? "") });
      return `Reconciliation ${r.data.reco_id} proposed: ${rupees(r.data.receipts_paise)}; ${rupees(r.data.summary.outstanding_after_paise)} would remain outstanding.`;
    });
  }
  function decide(r: Reco, decision: "APPROVE" | "REJECT") {
    void run(async () => {
      const token = await stepUp.ask({ action: "approve-pa-reco", resourceId: r.reco_id, amountPaise: r.receipts_paise,
        summary: `${decision === "APPROVE" ? "Approve" : "Reject"} ${r.reco_id}: ${rupees(r.receipts_paise)} of past accumulations` });
      if (!token) return "Cancelled.";
      const out = await command<Envelope<Reco>>("POST", `${base}/past-accumulation-vdr-reconciliations/${r.reco_id}/approvals`,
        { decision, note: decision === "APPROVE" ? "Receipts verified with the SE-6 statement" : "Receipts do not match the statement" }, { stepUpToken: token });
      return `${r.reco_id}: ${STATE[out.data.state] ?? out.data.state}.`;
    });
  }

  return <section className="card stack" aria-labelledby="pa-reco-heading"><h2 id="pa-reco-heading">Past accumulations — receipts reconciliation</h2>
    <p className="muted">A de-exempted trust transfers its past accumulations within 30 days: the cash by demand draft (a VDR entry), the SDS balance and
      the securities, confirmed by HO&apos;s Investment Division with a reference. Each receipt clears what the members were credited; the trust is
      reconciled when the receipts equal the credits and the Form SE-6 statement.</p>
    <ProblemMessage error={error ?? data.error} />
    {notice ? <p role="status">{notice}</p> : null}
    {data.data && !data.data.data.length ? <p className="muted">No trust&apos;s past accumulations have been credited yet.</p> : null}
    {data.data?.data.map((p) => <article key={p.establishment_id} className="stack">
      <h3>{p.legal_name} ({p.establishment_id})</h3>
      <dl className="kv"><div><dt>Credited to members</dt><dd>{rupees(p.credited_paise)}</dd></div><div><dt>Received</dt><dd>{rupees(p.received_paise)}</dd></div>
        <div><dt>Outstanding</dt><dd><strong>{rupees(p.outstanding_paise)}</strong></dd></div></dl>
      {p.reconciliations.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Reconciliation</th><th scope="col">Receipts</th>
        <th scope="col">Amount</th><th scope="col">SE-6 statement</th><th scope="col">State</th>{role === "fo.apfc" ? <th scope="col">Decision</th> : null}</tr></thead>
        <tbody>{p.reconciliations.map((r) => <tr key={r.reco_id}><th scope="row">{r.reco_id}</th>
          <td>{r.receipts.map((x) => `${x.component} ${x.reference}`).join("; ")}</td><td>{rupees(r.receipts_paise)}</td>
          <td>{rupees(r.statement_total_paise)}{r.summary.statement_difference_paise ? ` (differs by ${rupees(r.summary.statement_difference_paise)})` : ""}</td>
          <td>{STATE[r.state] ?? r.state}{r.state === "SHORT" ? ` — ${rupees(r.summary.outstanding_after_paise)} outstanding` : ""}</td>
          {role === "fo.apfc" ? <td>{r.state === "PROPOSED" ? <div className="actions">
            <button type="button" className="primary" disabled={busy} onClick={() => decide(r, "APPROVE")}>Approve</button>
            <button type="button" disabled={busy} onClick={() => decide(r, "REJECT")}>Reject</button></div> : "—"}</td> : null}</tr>)}</tbody></table></div> : null}
      {role === "fo.da_accounts" && p.outstanding_paise > 0 ? <form className="stack" aria-label={`Reconcile ${p.establishment_id}`} onSubmit={(e) => propose(e, p)}>
        <fieldset><legend>Demand drafts received (VDR)</legend>
          {p.unreconciled_receipts.length ? p.unreconciled_receipts.map((v) => <label key={v.vdr_id} className="check-row"><input type="checkbox" name="vdr" value={v.vdr_id} />
            {v.vdr_id} · {v.instrument} {v.instrument_ref} · {rupees(v.amount_paise)} · {v.received_on}</label>) : <p className="muted">No unreconciled receipt of this establishment.</p>}
        </fieldset>
        <div className="form-row"><label>SDS — Investment Division reference<input name="SDS_ref" /></label><label>SDS amount (₹)<input name="SDS_amount" type="number" min="0" step="0.01" /></label></div>
        <div className="form-row"><label>Securities — Investment Division reference<input name="SECURITIES_ref" /></label><label>Securities amount (₹)<input name="SECURITIES_amount" type="number" min="0" step="0.01" /></label></div>
        <div className="form-row"><label>Form SE-6 statement total (₹)<input name="statement" type="number" min="1" step="0.01" required /></label><label>Note<input name="note" /></label></div>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>Propose the reconciliation</button></div>
      </form> : null}
    </article>)}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
