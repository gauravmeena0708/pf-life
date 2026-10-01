import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

export interface InternalPara { para_id: string; report_id: string; office_id: string; category: string; observation: string; recommendation: string;
  amount_at_risk_paise: number; reply_due: string; state: string; overdue: boolean; replies: { reply: string; action_taken: string }[] }

export function InternalParas({ role }: { role: "fo.oic" | "ho.audit" }) {
  const { t } = useTranslation(); const qc = useQueryClient(); const stepUp = useStepUp();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState("");
  const paras = useQuery({ queryKey: ["internal-paras", role], queryFn: () => api<Envelope<InternalPara[]>>( "/api/v1/audit/internal/paras"), retry: false });
  async function submit(e: FormEvent<HTMLFormElement>, para: InternalPara) {
    e.preventDefault(); if (busy) return; const form = e.currentTarget; const f = new FormData(form); const value = (key: string) => String(f.get(key) ?? "").trim();
    const decision = role === "ho.audit"; const body = decision ? { decision: value("decision"), note: value("note") } : { reply: value("reply"), action_taken: value("action_taken"), request_drop: f.has("request_drop") };
    const token = decision ? await stepUp.ask({ action: "decide-audit-para", resourceId: para.para_id, summary: `Decide audit para ${para.para_id}.` }) : null;
    if (decision && !token) return;
    setBusy(true); setError(null); setNotice("");
    try {
      await command("POST", `/api/v1/audit/internal/paras/${encodeURIComponent(para.para_id)}/${decision ? "decisions" : "replies"}`, body, decision ? { stepUpToken: token! } : {});
      form.reset(); setNotice(`${para.para_id} ${decision ? "decided" : "replied to"}.`); await qc.invalidateQueries({ queryKey: ["internal-paras", role] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="audit-paras-heading"><h2 id="audit-paras-heading">Internal-audit paras</h2>
    <ProblemMessage error={error ?? paras.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {paras.data?.data.map((para) => <article className="card stack" key={para.para_id}><h3>{para.para_id} · {para.category}</h3>
      <p>{para.office_id} · {statusLabel(para.state, t)} {para.overdue ? <span className="state-pill">Overdue</span> : null} · Reply due {para.reply_due}</p>
      <p>{para.observation}</p><p>Recommendation: {para.recommendation}</p>
      {para.replies?.at(-1) ? <p>Office reply: {para.replies.at(-1)?.reply}</p> : null}
      {role === "fo.oic" && para.state === "OPEN" ? <form className="stack" aria-label={`Reply to para ${para.para_id}`} onSubmit={(e) => void submit(e, para)}>
        <label>Reply<textarea name="reply" required minLength={20} maxLength={4000} /></label><label>Action taken<textarea name="action_taken" required maxLength={4000} /></label>
        <label><input type="checkbox" name="request_drop" /> Request drop</label><div className="actions"><button className="primary" disabled={busy}>Send reply</button></div>
      </form> : null}
      {role === "ho.audit" && para.state === "REPLIED" ? <form className="stack" aria-label={`Decide para ${para.para_id}`} onSubmit={(e) => void submit(e, para)}>
        <label>Decision<select name="decision"><option value="DROP">Drop</option><option value="KEEP">Keep</option></select></label>
        <label>Decision note<textarea name="note" required maxLength={4000} /></label><div className="actions"><button className="primary" disabled={busy}>Decide</button></div>
      </form> : null}
    </article>)}{paras.data && !paras.data.data.length ? <p className="muted">No internal-audit paras.</p> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
