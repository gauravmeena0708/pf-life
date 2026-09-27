import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface SessionRow { session_id: string; subject: string; stakeholder: string; persona_label: string | null; created_at: number; last_seen: number; device: string; current: boolean }
interface Recovery { request_id: string; member_id: string; reason: string; state: string; current: { mobile_masked: string; email_masked: string };
  restore_to: { mobile_masked: string; email_masked: string }; decision_note: string | null; created_at: string | null }

const when = (seconds: number) => new Date(seconds * 1000).toLocaleString("en-IN");

/** Security analyst (interface 17, Journey D5): account-recovery reviews and session revocation, both with step-up. */
export function SessionsRecoveryPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const sessions = useQuery({ queryKey: ["all-sessions"], queryFn: () => api<Envelope<SessionRow[]>>("/api/v1/security/sessions"), retry: false, refetchInterval: 5000 });
  const recoveries = useQuery({ queryKey: ["recoveries"], queryFn: () => api<Envelope<Recovery[]>>("/api/v1/security/account-recovery-requests"), retry: false });

  async function run(work: () => Promise<unknown>, ok: string) {
    setError(null); setNotice(null);
    try {
      await work();
      setNotice(ok);
      await qc.invalidateQueries({ queryKey: ["all-sessions"] });
      await qc.invalidateQueries({ queryKey: ["recoveries"] });
    } catch (cause) { setError(cause); }
  }

  async function revoke(s: SessionRow) {
    const token = await stepUp.ask({ action: "revoke-session", resourceId: s.session_id,
      summary: `Sign out session ${s.session_id} of ${s.persona_label ?? s.subject} immediately.` });
    if (token) await run(() => command("POST", `/api/v1/security/sessions/${s.session_id}/revocations`, undefined, { stepUpToken: token }), "Session revoked.");
  }

  async function decide(e: FormEvent<HTMLFormElement>, r: Recovery) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const decision = String(form.get("decision"));
    const token = await stepUp.ask({ action: "decide-recovery", resourceId: r.request_id,
      summary: decision === "APPROVE" ? `Approve recovery ${r.request_id}: restore ${r.restore_to.mobile_masked} / ${r.restore_to.email_masked}.`
        : `Reject recovery ${r.request_id}; nothing changes.` });
    if (token) await run(() => command("POST", `/api/v1/security/account-recovery-requests/${r.request_id}/decisions`,
      { decision, note: String(form.get("note")).trim() }, { stepUpToken: token }), `Recovery ${r.request_id} decided.`);
  }

  return (
    <section className="stack" aria-labelledby="sr-heading">
      <PageHeader id="sr-heading" eyebrow="Security operations · Journey D" title="Sessions and account recovery"
        description="Review recovery requests and sign out sessions. Session IDs never leave the gateway; you see a one-way handle."
        current="Sessions & recovery" />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      <section className="card stack" aria-labelledby="rec-heading">
        <h2 id="rec-heading">Account-recovery requests</h2>
        <ProblemMessage error={recoveries.error} />
        {recoveries.data?.data.length === 0 ? <p className="muted">No requests.</p> : null}
        {recoveries.data?.data.map((r) => (
          <article key={r.request_id} className="profile-card stack">
            <div className="section-heading"><h3>{r.request_id} · member {r.member_id}</h3><span className="state-pill">{r.state.replaceAll("_", " ").toLowerCase()}</span></div>
            <p>{r.reason}</p>
            <dl className="kv"><dt>Now</dt><dd>{r.current.mobile_masked} · {r.current.email_masked}</dd>
              <dt>Would restore</dt><dd>{r.restore_to.mobile_masked} · {r.restore_to.email_masked} (last verified)</dd></dl>
            {r.state === "PENDING_REVIEW" ? (
              <form className="stack" onSubmit={(e) => void decide(e, r)}>
                <fieldset className="case-options"><legend>Decision</legend>
                  <label className="check-row"><input type="radio" name="decision" value="APPROVE" required />Approve and restore verified contact details</label>
                  <label className="check-row"><input type="radio" name="decision" value="REJECT" />Reject</label>
                </fieldset>
                <label>How you verified the member<textarea name="note" required minLength={10} maxLength={2000} /></label>
                <div className="actions"><button type="submit" className="primary">Record decision</button></div>
              </form>
            ) : r.decision_note ? <p className="muted">Note: {r.decision_note}</p> : null}
          </article>
        ))}
      </section>
      <section className="card stack" aria-labelledby="sessions-heading">
        <h2 id="sessions-heading">Active sessions</h2>
        <ProblemMessage error={sessions.error} />
        <div className="table-scroll"><table>
          <thead><tr><th scope="col">Session</th><th scope="col">Who</th><th scope="col">Role</th><th scope="col">Device</th><th scope="col">Signed in</th><th scope="col">Last seen</th><th /></tr></thead>
          <tbody>{sessions.data?.data.map((s) => (
            <tr key={s.session_id}>
              <td><code>{s.session_id}</code></td><td>{s.persona_label ?? s.subject}</td><td>{s.stakeholder}</td><td><code>{s.device}</code></td>
              <td>{when(s.created_at)}</td><td>{when(s.last_seen)}</td>
              <td>{s.current ? <span className="muted small">this session</span> : <button type="button" onClick={() => void revoke(s)}>Revoke</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </section>
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
