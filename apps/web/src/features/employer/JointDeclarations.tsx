import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Jd { case_id: string; version: number; subject_ref: string; state: string; data: Record<string, string> }
const PARAMETERS = ["NAME", "DATE_OF_BIRTH", "GENDER", "FATHER_NAME", "MOTHER_NAME", "MARITAL_STATUS", "NATIONALITY", "DATE_OF_JOINING"];

/** Employer attestation of members' Joint Declarations (the employer confirms what its records show). */
export function JointDeclarations() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const signatory = session.data?.stakeholder === "employer.signatory";
  const disabled = busy || !!stepUp.request;
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

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!signatory) return;
    const form = e.currentTarget; const f = new FormData(form);
    const value = (key: string) => String(f.get(key) ?? "").trim();
    const uan = value("uan");
    const body = { uan, parameter: value("parameter"), current_value: value("current_value"), corrected_value: value("corrected_value"),
      reason: value("reason"), ...(value("document_ref") ? { document_ref: value("document_ref") } : {}), member_consent: "MOCK_AADHAAR_OTP" };
    setBusy(true); setError(null); setNotice(null);
    try {
      if (body.reason.length < 10) throw new Error("Enter a reason of at least 10 characters.");
      if (f.get("consent") !== "on") throw new Error("Confirm the member's mock Aadhaar OTP consent.");
      const token = await stepUp.ask({ action: "submit-joint-declaration-employer", resourceId: uan,
        summary: `Submit a Joint Declaration for UAN ${uan}: change ${body.parameter.replaceAll("_", " ")} from ${body.current_value} to ${body.corrected_value}, with member consent by mock Aadhaar OTP.` });
      if (!token) return;
      const r = await command<Envelope<{ case_id: string }>>("POST", "/api/v1/employers/me/joint-declarations", body, { stepUpToken: token });
      form.reset();
      setNotice(`Employer-initiated Joint Declaration ${r.data.case_id} submitted with mock member consent.`);
      await Promise.all([qc.invalidateQueries({ queryKey: ["employer-jds"] }),
        qc.invalidateQueries({ queryKey: ["employer-pending-approvals"] })]);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return (
    <section className="card stack" aria-labelledby="jd-heading">
      <h2 id="jd-heading">Members' correction requests (Joint Declarations)</h2>
      <ProblemMessage error={list.error} />
      <ProblemMessage error={error ?? session.error} />
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
          <div className="actions"><button type="submit" className="primary" disabled={disabled}>Record (one-time code)</button></div>
        </form>
      ))}
      {signatory ? <form className="card stack" aria-labelledby="employer-jd-heading" onSubmit={(e) => void submit(e)}>
        <h2 id="employer-jd-heading">Employer-initiated JD</h2>
        <p className="muted">Submit a Joint Declaration with the member's consent. Aadhaar OTP consent is simulated in this demonstration.</p>
        <fieldset className="stack" disabled={disabled}><legend>Joint Declaration details</legend>
          <div className="form-row">
            <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
            <label>Parameter<select name="parameter" required>{PARAMETERS.map((parameter) => <option key={parameter} value={parameter}>
              {parameter.replaceAll("_", " ")}</option>)}</select></label>
            <label>Current value<input name="current_value" required maxLength={120} /></label>
            <label>Corrected value<input name="corrected_value" required maxLength={120} /></label>
          </div>
          <label>Reason<textarea name="reason" required minLength={10} maxLength={1000} /></label>
          <label>Document reference (optional)<input name="document_ref" maxLength={200} /></label>
          <label className="check-row"><input type="checkbox" name="consent" required />Member consent confirmed by Aadhaar OTP (mock)</label>
        </fieldset>
        <div className="actions"><button type="submit" className="primary" disabled={disabled}>Submit employer Joint Declaration with DSC / e-sign</button></div>
      </form> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
