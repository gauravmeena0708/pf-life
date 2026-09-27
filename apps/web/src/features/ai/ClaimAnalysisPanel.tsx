import { useState } from "react";

import { command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { FeedbackButtons } from "./FeedbackButtons";

interface Analysis {
  analysis_type: string; advisory_only: boolean; summary: string; evidence_references: string[]; uncertainties: string[];
  suggested_next_step: string; model_id: string; policy_version: string; mode: "llm" | "rules"; guidance: string[];
  requires_officer_review: boolean; interaction_id: string;
}

/** Advisory claim analysis for the dealing assistant (Journey E3). It never approves, rejects or changes anything. */
export function ClaimAnalysisPanel({ claimId }: { claimId: string }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null);
    try {
      setAnalysis((await command<Envelope<Analysis>>("POST", "/api/v1/ai/claims/analyse", { claim_id: claimId })).data);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return (
    <section className="card stack" aria-labelledby="analysis-heading">
      <div className="section-heading">
        <div><p className="eyebrow">Advisory only · requires officer review</p><h2 id="analysis-heading">Assistant analysis</h2></div>
        {analysis ? <span className="state-pill">{analysis.mode === "llm" ? "model-assisted" : "rules only (model off)"}</span> : null}
      </div>
      <ProblemMessage error={error} />
      {!analysis ? (
        <div className="actions"><button type="button" onClick={() => void run()} disabled={busy}>Get advisory analysis</button></div>
      ) : (
        <>
          <p>{analysis.summary}</p>
          <dl className="kv">
            <dt>Evidence</dt><dd>{analysis.evidence_references.map((e) => <code key={e}>{e} </code>)}</dd>
            <dt>Guidance</dt><dd>{analysis.guidance.map((g) => <code key={g}>{g} </code>)}</dd>
            <dt>Next step</dt><dd>{analysis.suggested_next_step}</dd>
            <dt>Versions</dt><dd>{analysis.policy_version} · model {analysis.model_id}</dd>
          </dl>
          {analysis.uncertainties.length ? <ul className="small">{analysis.uncertainties.map((u) => <li key={u}>{u}</li>)}</ul> : null}
          <p className="demo-tip">This analysis cannot approve, reject or change the claim. The decision and its reasons are yours.</p>
          <FeedbackButtons interactionId={analysis.interaction_id} />
        </>
      )}
    </section>
  );
}
