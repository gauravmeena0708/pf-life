import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime, stateLabel } from "../journeyB";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { GrievanceThread } from "./GrievanceThread";
import { TriageSuggestion } from "./TriageSuggestion";
import type { Grievance } from "./types";

const TIER_OF: Record<string, string> = { "fo.pro": "RO", "zo.acc": "ZO" };

/** Office view of a grievance (Journey C3–C4): reply, link evidence, escalate, resolve with step-up. */
export function GrievanceOfficePage() {
  const { t, i18n } = useTranslation();
  const { grievanceId } = useParams();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const detail = useQuery({ queryKey: ["office-grievance", grievanceId], enabled: !!grievanceId, retry: false,
    queryFn: () => api<Envelope<Grievance>>(`/api/v1/grievances/${grievanceId}`) });
  const g = detail.data?.data;
  const role = session.data?.stakeholder ?? "";
  const handling = !!g && TIER_OF[role] === g.tier && !["RESOLVED", "CLOSED"].includes(g.state);

  async function run(work: () => Promise<unknown>, ok: string, form?: HTMLFormElement) {
    setBusy(true); setError(null); setNotice(null);
    try {
      await work();
      form?.reset();
      setNotice(ok);
      await qc.invalidateQueries({ queryKey: ["office-grievance", grievanceId] });
      await qc.invalidateQueries({ queryKey: ["office-work-queue"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  const field = (e: FormEvent<HTMLFormElement>, name: string) => String(new FormData(e.currentTarget).get(name)).trim();
  const post = (path: string, body: unknown, stepUpToken?: string) =>
    command("POST", `/api/v1/grievances/${grievanceId}/${path}`, body, { stepUpToken });

  async function resolve(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!g) return;
    const form = e.currentTarget;
    const resolution = field(e, "resolution");
    const token = await stepUp.ask({ action: "resolve-grievance", resourceId: g.grievance_id, resourceVersion: g.version,
      summary: `Resolve grievance ${g.grievance_id}. The member is told the outcome and may reopen it within 30 days.` });
    if (!token) return;
    await run(() => post("resolution", { resolution }, token), "Grievance resolved; the member has been notified.", form);
  }

  return (
    <section className="stack" aria-labelledby="office-grievance-heading">
      <PageHeader id="office-grievance-heading" eyebrow="Regional office · Journey C" title={g ? g.subject : "Grievance"}
        description={g ? `${g.grievance_id} · ${g.category} · office ${g.office_id}` : ""} current={g?.grievance_id ?? "Grievance"}
        parent={{ label: "Work queue", to: "/office/work-queue" }}>
        {g ? <span className="state-pill">{stateLabel(g.state, t)}</span> : null}
      </PageHeader>
      <ProblemMessage error={detail.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {g ? (
        <>
          <section className="card stack" aria-labelledby="og-summary">
            <h2 id="og-summary">Complaint</h2>
            <p>{g.description}</p>
            <dl className="kv">
              <dt>Handled at</dt><dd>{g.tier}</dd>
              <dt>Due by</dt><dd>{dateTime(g.sla_due_at, i18n.language)}</dd>
              <dt>Linked claim</dt><dd>{g.linked_claim_id ? <code>{g.linked_claim_id}</code> : "—"}</dd>
            </dl>
            {!handling && !["RESOLVED", "CLOSED"].includes(g.state) ? <p className="demo-tip">This grievance is currently handled at the {g.tier} tier. You can read it but not act on it.</p> : null}
          </section>
          {role === "fo.pro" ? <TriageSuggestion text={`${g.subject}. ${g.description}`} current={g.category} /> : null}
          <GrievanceThread grievance={g} viewer="office" />
          {handling ? (
            <div className="activity-columns">
              <form className="card stack" onSubmit={(e) => { e.preventDefault(); const f = e.currentTarget; void run(() => post("messages", { body: field(e, "body") }), "Reply sent to the member.", f); }}>
                <h2>Reply to the member</h2>
                <p className="muted small">Your first reply takes the grievance up (status: in progress).</p>
                <label>Reply<textarea name="body" required minLength={2} maxLength={4000} /></label>
                <div className="actions"><button type="submit" className="primary" disabled={busy}>Send reply</button></div>
              </form>
              {role === "fo.pro" ? (
                <form className="card stack" onSubmit={(e) => {
                  e.preventDefault(); const f = e.currentTarget;
                  const refs = field(e, "refs").split(/[\s,]+/).filter(Boolean);
                  void run(() => post("evidence-links", { evidence_refs: refs, note: field(e, "note") }), "Evidence linked.", f);
                }}>
                  <h2>Link case evidence</h2>
                  <label>Evidence IDs (claim, case, payment or journal IDs)<input name="refs" required defaultValue={g.linked_claim_id ?? ""} /></label>
                  <label>What it shows<textarea name="note" required minLength={2} maxLength={1000} /></label>
                  <div className="actions"><button type="submit" disabled={busy}>Link evidence</button></div>
                </form>
              ) : null}
              {g.state === "IN_PROGRESS" ? (
                <form className="card stack" onSubmit={(e) => void resolve(e)}>
                  <h2>Resolve</h2>
                  <p className="muted small">Needs a one-time code. Explain the outcome in plain words.</p>
                  <label>Resolution<textarea name="resolution" required minLength={10} maxLength={4000} /></label>
                  <div className="actions"><button type="submit" className="primary" disabled={busy}>Resolve grievance</button></div>
                </form>
              ) : null}
              {g.tier !== "HO" && ["ROUTED", "IN_PROGRESS"].includes(g.state) ? (
                <form className="card stack" onSubmit={(e) => { e.preventDefault(); const f = e.currentTarget; void run(() => post("escalations", { reason: field(e, "reason") }), "Escalated to the next tier.", f); }}>
                  <h2>Escalate</h2>
                  <label>Why the next tier must handle it<textarea name="reason" required minLength={5} maxLength={1000} /></label>
                  <div className="actions"><button type="submit" disabled={busy}>Escalate</button></div>
                </form>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
