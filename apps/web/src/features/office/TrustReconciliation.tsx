import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Submission { annexure_id: string; transfer_id: string; uan: string; from_account_link_id: string; to_account_link_id: string;
  state: string; submitted_total_paise: number; service_from?: string | null; service_to?: string | null; breaks_months?: number | null }
interface Result { annexure_id: string; state: string; difference_paise: number; received_paise: number }

/** The DA (Accounts) reconciles the Annexure K an exempted trust sent for a transfer into this office's member IDs (P2.9b). */
export function TrustReconciliation() {
  const { t } = useTranslation(); const stepUp = useStepUp(); const qc = useQueryClient();
  const [result, setResult] = useState<Result | null>(null); const [error, setError] = useState<unknown>(null); const [busy, setBusy] = useState(false);
  const pending = useQuery({ queryKey: ["trust-annexure-k"], retry: false, queryFn: async () => {
    const [submitted, mismatched] = await Promise.all(["SUBMITTED", "MISMATCH"].map((state) =>
      api<Envelope<{ annexure_k: Submission[] }>>(`/api/v1/office/exempted/annexure-k?state=${state}`)));
    return [...submitted.data.annexure_k, ...mismatched.data.annexure_k]; } });
  const submit = (item: Submission) => (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const f = new FormData(event.currentTarget);
    const received = Math.round(Number(f.get("received")) * 100); const receipt = String(f.get("receipt_ref")).trim();
    setError(null); setResult(null); setBusy(true);
    void (async () => { try { const token = await stepUp.ask({ action: "reconcile-trust-annexure-k", resourceId: item.annexure_id,
      amountPaise: item.submitted_total_paise,
      summary: `Reconcile trust Annexure K ${item.annexure_id}: submitted ${rupees(item.submitted_total_paise)}, received ${rupees(received)}.` });
      if (!token) return;
      const r = await command<Envelope<Result>>("POST", `/api/v1/office/exempted/annexure-k/${encodeURIComponent(item.annexure_id)}/reconciliations`,
        { receipt_ref: receipt, received_paise: received }, { stepUpToken: token });
      setResult(r.data); await qc.invalidateQueries({ queryKey: ["trust-annexure-k"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); } })();
  };
  const items = pending.data ?? [];
  return <section className="card stack" aria-labelledby="trust-reconciliation-heading"><h2 id="trust-reconciliation-heading">Annexure K from exempted trusts</h2>
    <p className="muted small">Transfers out of an exempted trust into this office's member IDs: match the trust's Annexure K with the amount received.
      Once matched, the PF is credited and the pension (EPS) service follows on its own.</p>
    <ProblemMessage error={pending.error ?? error} />
    {pending.isLoading ? <p role="status">Loading…</p> : null}
    {!pending.isLoading && !items.length ? <p className="muted">Nothing awaits reconciliation.</p> : null}
    {items.map((item) => <article className="stack" key={item.annexure_id} aria-label={`Annexure K ${item.annexure_id}`}>
      <p><strong>{item.annexure_id}</strong> · UAN <code>{item.uan}</code> · {item.from_account_link_id} → {item.to_account_link_id} ·
        <span className="state-pill">{statusLabel(item.state, t)}</span></p>
      <p className="muted small">Submitted {rupees(item.submitted_total_paise)}{item.service_from ? ` · service ${item.service_from} – ${item.service_to ?? ""}` : ""}
        {item.breaks_months ? ` · breaks ${item.breaks_months} months` : ""}</p>
      <form className="form-row" aria-label={`Reconcile ${item.annexure_id}`} onSubmit={submit(item)}>
        <label>Receipt reference<input name="receipt_ref" required maxLength={100} /></label>
        <label>Amount received (₹)<input name="received" type="number" min="0" step="0.01" required defaultValue={(item.submitted_total_paise / 100).toFixed(2)} /></label>
        <div className="actions"><button type="submit" className="primary" disabled={busy}>Reconcile</button></div></form>
    </article>)}
    {result ? <p role="status"><strong>{result.annexure_id}: <span className="state-pill">{statusLabel(result.state, t)}</span></strong> · Difference {rupees(result.difference_paise)}</p> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
