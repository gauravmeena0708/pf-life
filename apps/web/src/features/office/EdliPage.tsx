import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface EdliClaim {
  claim_id: string; death_of_uan: string; amount_paise: number; version: number;
  summary: string; working: string | null; service_months: number;
}
interface Benefit { amount_paise: number; working: string; filed_amount_paise: number; version: number }

function ClaimDecision({ claim }: { claim: EdliClaim }) {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [wages, setWages] = useState("");
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<Benefit | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const disabled = busy || !!stepUp.request;
  const base = `/api/v1/office/edli-claims/${encodeURIComponent(claim.claim_id)}`;

  async function run(decision: "PREVIEW" | "APPROVE" | "REJECT") {
    if (disabled) return;
    setBusy(true); setError(null);
    if (decision === "PREVIEW") setPreview(null);
    try {
      const paise = Math.round(Number(wages) * 100);
      if (decision !== "REJECT" && (!/^\d+(\.\d{1,2})?$/.test(wages) || !Number.isSafeInteger(paise) || paise <= 0))
        throw new Error("Enter positive monthly wages in rupees, with at most two decimal places.");
      if (decision === "PREVIEW") {
        setPreview((await command<Envelope<Benefit>>("POST", `${base}/benefit-previews`, { average_monthly_wages_paise: paise })).data);
        return;
      }
      if (reason.trim().length < 10) throw new Error("Enter a reason of at least 10 characters.");
      if (decision === "APPROVE" && !preview) throw new Error("Work out the benefit before approving the claim.");
      const token = await stepUp.ask({ action: "decide-edli", resourceId: claim.claim_id,
        resourceVersion: decision === "APPROVE" ? preview!.version : claim.version,
        ...(decision === "APPROVE" ? { amountPaise: preview!.amount_paise } : {}),
        summary: `${decision === "APPROVE" ? `Approve EDLI benefit of ${rupees(preview!.amount_paise)}` : "Reject EDLI claim"} ${claim.claim_id}. ${reason.trim()}` });
      if (!token) return;
      await command("POST", `${base}/decisions`, { decision, reason: reason.trim(),
        ...(decision === "APPROVE" ? { average_monthly_wages_paise: paise } : {}) }, { stepUpToken: token });
      setPreview(null);
      await qc.invalidateQueries({ queryKey: ["office-edli"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <article className="card stack"><h2>EDLI claim {claim.claim_id}</h2><p>{claim.summary}</p>
    <dl className="kv"><dt>Deceased member UAN</dt><dd>{claim.death_of_uan}</dd><dt>Filed amount</dt><dd>{rupees(claim.amount_paise)}</dd>
      <dt>Service (months)</dt><dd>{claim.service_months}</dd><dt>Version</dt><dd>{claim.version}</dd></dl>
    {claim.working ? <p>{claim.working}</p> : null}<ProblemMessage error={error} />
    <form className="stack" aria-label={`Decide EDLI claim ${claim.claim_id}`} onSubmit={(e) => { e.preventDefault(); void run("APPROVE"); }}>
      <fieldset className="stack" disabled={disabled}><legend>Verified benefit and decision</legend>
        <label>Verified average monthly wages (rupees)<input type="number" min="0.01" step="0.01" value={wages}
          onChange={(e) => { setWages(e.target.value); setPreview(null); }} /></label>
        <div className="actions"><button type="button" onClick={() => void run("PREVIEW")}>Work out benefit</button></div>
        {preview ? <div role="status"><p><strong>Benefit: {rupees(preview.amount_paise)}</strong> · Filed amount: {rupees(preview.filed_amount_paise)}</p>
          <p>{preview.working}</p><p>Version: {preview.version}</p></div> : null}
        <label>Decision reason<textarea required minLength={10} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <div className="actions"><button type="submit" className="primary" disabled={!preview}>Approve</button>
          <button type="button" onClick={() => void run("REJECT")}>Reject</button></div>
      </fieldset>
    </form>
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </article>;
}

export function EdliPage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = session.data?.stakeholder === "fo.edli";
  const claims = useQuery({ queryKey: ["office-edli"], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<EdliClaim[]>>("/api/v1/office/edli-claims") });
  return <section className="stack" aria-labelledby="edli-heading">
    <PageHeader id="edli-heading" eyebrow="EDLI section" title="EDLI claims" current="EDLI claims"
      description="Verify average wages, work out the benefit and record a decision." />
    <ProblemMessage error={session.error ?? claims.error} />
    {session.isLoading || claims.isLoading ? <p role="status">Loading EDLI claims…</p> : null}
    {session.data && !allowed ? <p className="pending-notice">This service is available to the EDLI section officer.</p> : null}
    {allowed ? claims.data?.data.map((claim) => <ClaimDecision key={`${claim.claim_id}-${claim.version}`} claim={claim} />) : null}
    {claims.data && !claims.data.data.length ? <p className="muted">No EDLI claims awaiting a decision.</p> : null}
  </section>;
}
