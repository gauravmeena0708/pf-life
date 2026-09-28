import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Jd { case_id: string; version: number; subject_ref: string; state: string; data: Record<string, string> }

/** Employer attestation of members' Joint Declarations (the employer confirms what its records show). */
export function JointDeclarations() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["employer-jds"], retry: false,
    queryFn: () => api<Envelope<Jd[]>>("/api/v1/employers/me/joint-declarations") });

  async function decide(e: FormEvent<HTMLFormElement>, jd: Jd) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const decision = String(f.get("decision"));
    const token = await stepUp.ask({ action: "attest-joint-declaration", resourceId: jd.case_id, resourceVersion: jd.version,
      summary: `${decision === "ATTEST" ? "Attest" : decision === "RETURN" ? "Return" : "Reject"} the correction of ${jd.data.parameter.replaceAll("_", " ").toLowerCase()} for UAN ${jd.subject_ref}.` });
    if (!token) return;
    setError(null);
    try {
      await command("POST", `/api/v1/employers/me/joint-declarations/${jd.case_id}/decisions`, { decision, note: String(f.get("note")).trim() },
                    { stepUpToken: token });
      setNotice(`Recorded for ${jd.case_id}.`);
      await qc.invalidateQueries({ queryKey: ["employer-jds"] });
    } catch (cause) { setError(cause); }
  }

  return (
    <section className="card stack" aria-labelledby="jd-heading">
      <h2 id="jd-heading">Members' correction requests (Joint Declarations)</h2>
      <ProblemMessage error={list.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {list.data?.data.length === 0 ? <p className="muted">Nothing is waiting for your attestation.</p> : null}
      {list.data?.data.map((jd) => (
        <form key={jd.case_id} className="profile-card stack" onSubmit={(e) => void decide(e, jd)}>
          <h3>{jd.data.parameter.replaceAll("_", " ").toLowerCase()} · UAN <code>{jd.subject_ref}</code></h3>
          <dl className="kv"><dt>Now</dt><dd>{jd.data.current_value}</dd><dt>Corrected</dt><dd><strong>{jd.data.corrected_value}</strong></dd>
            <dt>Member's reason</dt><dd>{jd.data.reason}</dd><dt>Approved by</dt><dd>{jd.data.change_class === "MAJOR" ? "APFC (major change)" : "Accounts officer (minor change)"}</dd></dl>
          <fieldset className="case-options"><legend>Your records</legend>
            <label className="check-row"><input type="radio" name="decision" value="ATTEST" required />Attest — our records support the correction</label>
            <label className="check-row"><input type="radio" name="decision" value="RETURN" />Return — the member must correct the request</label>
            <label className="check-row"><input type="radio" name="decision" value="REJECT" />Reject — our records do not support it</label>
          </fieldset>
          <label>Note<textarea name="note" required minLength={5} maxLength={1000} /></label>
          <div className="actions"><button type="submit" className="primary">Record (one-time code)</button></div>
        </form>
      ))}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
