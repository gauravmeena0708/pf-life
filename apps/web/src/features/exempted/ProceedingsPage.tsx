import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { ProceedingView, type Proceeding } from "./ProceedingView";

const stages = ["", "APPLIED", "SHOW_CAUSE_ISSUED", "REPLIED", "RELINQUISHED", "UNEXEMPTED_COMPLIANCE", "AT_ZO", "AT_HO", "EEC_RECOMMENDED", "CBT_RATIFIED", "SENT_TO_GOVERNMENT", "NOTIFIED", "RETURNED", "DROPPED", "CLOSED"];
export function ProceedingsQueue() {
  const { t } = useTranslation(); const qc = useQueryClient(); const stepUp = useStepUp();
  const [stage, setStage] = useState(""); const [selectedId, setSelectedId] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState("");
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false }); const role = session.data?.stakeholder;
  const path = `/api/v1/office/exempted/proceedings${stage ? `?stage=${encodeURIComponent(stage)}` : ""}`;
  const queue = useQuery({ queryKey: ["exemption-proceedings", stage], queryFn: () => api<Envelope<Proceeding[]>>(path), enabled: !!role && ["fo.exemption", "fo.oic", "zo.acc", "ho.exemption"].includes(role), retry: false });
  const selected = queue.data?.data.find((item) => item.proceeding_id === selectedId) ?? null;
  const due = selected?.what_is_due_next.filter((item) => item.role === role && !(item.step === "AGENDA_TO_ZO" && selected.stage === "SHOW_CAUSE_ISSUED" && !item.overdue) &&
    !(item.step === "RETURN_INCOMPLETE" && selected.kind !== "SURRENDER") && !(item.step === "DROP" && selected.kind !== "CANCELLATION")) ?? [];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected || !role) return; const f = new FormData(event.currentTarget); const step = String(f.get("step"));
    if (!due.some((item) => item.step === step)) return;
    const note = String(f.get("note") || "").trim(); const reference = String(f.get("reference") || "").trim() || null; const date = String(f.get("date") || "") || null;
    const ho = role === "ho.exemption"; const resourceId = ho ? selected.establishment_id : selected.proceeding_id;
    const body = ho ? { decision: step, note, reference, date } : { step, note, reference, date: step === "PERMIT_UNEXEMPTED" && selected.kind === "CANCELLATION" ? date : null };
    setBusy(true); setError(null); setNotice("");
    try { const token = await stepUp.ask({ action: ho ? "exemption-decision" : "exemption-step", resourceId, summary: `${statusLabel(step, t)} for ${selected.establishment_id}: ${note}` });
      if (!token) return;
      await command("POST", ho ? `/api/v1/ho/exemptions/${encodeURIComponent(resourceId)}/decisions` : `/api/v1/office/exempted/proceedings/${encodeURIComponent(resourceId)}/steps`, body, { stepUpToken: token });
      setNotice(`${statusLabel(step, t)} recorded.`); await qc.invalidateQueries({ queryKey: ["exemption-proceedings"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="exemption-proceedings-heading"><h2 id="exemption-proceedings-heading">Exemption proceedings</h2>
    <ProblemMessage error={error ?? queue.error ?? session.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    <label>Stage filter<select value={stage} onChange={(e) => { setStage(e.target.value); setSelectedId(""); }}>{stages.map((value) => <option key={value} value={value}>{value ? statusLabel(value, t) : "All stages"}</option>)}</select></label>
    {queue.isLoading ? <p role="status">Loading proceedings…</p> : null}{queue.data?.data.length === 0 ? <p className="muted">No proceedings in this queue.</p> : null}
    {queue.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Establishment</th><th scope="col">Kind</th><th scope="col">Stage</th><th scope="col">Due by</th><th scope="col">Overdue</th></tr></thead><tbody>
      {queue.data.data.map((item) => <tr key={item.proceeding_id}><th scope="row"><button type="button" aria-pressed={selectedId === item.proceeding_id} onClick={() => setSelectedId(item.proceeding_id)}>{item.establishment_id}</button></th><td>{statusLabel(item.kind, t)}</td><td>{statusLabel(item.stage, t)}</td><td>{item.due_by || "—"}</td><td>{item.overdue ? <strong className="proceeding-overdue">Overdue</strong> : "—"}</td></tr>)}
    </tbody></table></div> : null}
    {selected ? <><ProceedingView proceeding={selected} />{due.length ? <form className="stack" aria-label={`Act on proceeding ${selected.proceeding_id}`} onSubmit={(e) => void submit(e)}>
      <label>{role === "ho.exemption" ? "Decision" : "Step"}<select name="step" required>{due.map((item) => <option key={item.step} value={item.step}>{statusLabel(item.step, t)}</option>)}</select></label>
      <label>Note<textarea name="note" required /></label><label>{role === "ho.exemption" && due.length === 1 && due[0].step === "GOVERNMENT_NOTIFIED" ? "Notification number" : "Reference"}<input name="reference" required={role === "ho.exemption" && due.length === 1 && due[0].step === "GOVERNMENT_NOTIFIED"} /></label>
      {role === "ho.exemption" ? <label>{due.length === 1 && due[0].step === "GOVERNMENT_NOTIFIED" ? "Effective date" : "Date"}<input name="date" type="date" required={due.length === 1 && due[0].step === "GOVERNMENT_NOTIFIED"} /></label> : role === "fo.oic" && selected.kind === "CANCELLATION" ? <label>Effective date<input name="date" type="date" required /></label> : null}
      <button className="primary" disabled={busy || !!stepUp.request} type="submit">Record {role === "ho.exemption" ? "decision" : "step"}</button></form> : <p className="muted">No action is due for your role.</p>}</> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
export function ProceedingsPage() { return <section className="stack"><PageHeader id="proceedings-page-heading" eyebrow="Exemption" title="Exemption proceedings" current="Exemption proceedings" description="Review the next action and history of each exemption proceeding." /><ProceedingsQueue /></section>; }
