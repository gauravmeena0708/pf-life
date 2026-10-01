import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface PrivacyItem { request_id: string; kind: string; state: string; due_on: string; overdue: boolean; member_reference: string }
export function PrivacyRequestsPage() {
  const { t } = useTranslation(); const qc = useQueryClient(); const stepUp = useStepUp();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState("");
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const queue = useQuery({ queryKey: ["privacy-queue"], queryFn: () => api<Envelope<PrivacyItem[]>>( "/api/v1/privacy/requests"), retry: false });
  async function decide(e: FormEvent<HTMLFormElement>, item: PrivacyItem) {
    e.preventDefault(); if (busy) return; const form = e.currentTarget; const f = new FormData(form); const value = (key: string) => String(f.get(key) ?? "").trim();
    const decision = value("decision"); const legal_basis = value("legal_basis");
    if (decision !== "FULFILLED" && !legal_basis) { setError(new Error("Legal basis is required for this decision.")); return; }
    const token = await stepUp.ask({ action: "decide-privacy-request", resourceId: item.request_id, summary: `Decide data-principal request ${item.request_id}.` });
    if (!token) return;
    setBusy(true); setError(null); setNotice("");
    try {
      await command("POST", `/api/v1/privacy/requests/${encodeURIComponent(item.request_id)}/decisions`, { decision, answer: value("answer"), legal_basis: legal_basis || null }, { stepUpToken: token });
      form.reset(); setNotice(`${item.request_id} decided.`); await qc.invalidateQueries({ queryKey: ["privacy-queue"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack" aria-labelledby="privacy-heading"><PageHeader id="privacy-heading" eyebrow="Data protection office" title="Data-principal requests" description="Review and answer members' requests about their personal data." current="Data-principal requests" />
    <ProblemMessage error={error ?? queue.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    <section className="card stack" aria-labelledby="privacy-queue-heading"><h2 id="privacy-queue-heading">Request queue</h2>
      {queue.data?.data.map((item) => <article className="card stack" key={item.request_id}><h3>{item.request_id} · {statusLabel(item.kind, t)}</h3>
        <p>Member {item.member_reference} · {statusLabel(item.state, t)} {item.overdue ? <span className="state-pill">Overdue</span> : null} · Due {item.due_on}</p>
        {item.state === "OPEN" ? <form className="stack" aria-label={`Decide request ${item.request_id}`} onSubmit={(e) => void decide(e, item)}>
          <label>Decision<select name="decision" value={decisions[item.request_id] ?? "FULFILLED"} onChange={(e) => setDecisions({ ...decisions, [item.request_id]: e.target.value })}>
            <option value="FULFILLED">Fulfilled</option><option value="PARTLY_FULFILLED">Partly fulfilled</option><option value="REJECTED">Rejected</option></select></label>
          <label>Answer<textarea name="answer" required minLength={20} maxLength={4000} /></label>
          {decisions[item.request_id] && decisions[item.request_id] !== "FULFILLED" ? <label>Legal basis<textarea name="legal_basis" required maxLength={4000} /></label> : null}
          <div className="actions"><button className="primary" disabled={busy}>Decide</button></div>
        </form> : null}
      </article>)}{queue.data && !queue.data.data.length ? <p className="muted">No data-principal requests.</p> : null}
    </section><StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
