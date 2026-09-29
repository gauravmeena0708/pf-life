import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getMyPermissions, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { PendingApprovals } from "./SignaturePanels";

interface CaseItem { case_id: string; subject_ref: string; state: string; version: number; data: Record<string, string> }

/** Member › Member Profile (mark exit), Member › Approvals (the signatory approves exits) and
 * Online Services › Transfer Claims (attest a member's Form 13 transfer). */
export function MemberActionsPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  useQuery({ queryKey: ["my-permissions"], queryFn: getMyPermissions, retry: false });
  const role = session.data?.stakeholder;
  const signatory = role === "employer.signatory";
  const approvals = useQuery({ queryKey: ["employer-approvals"], enabled: signatory, retry: false,
    queryFn: () => api<Envelope<CaseItem[]>>("/api/v1/employers/me/approvals") });
  const transfers = useQuery({ queryKey: ["employer-transfers"], enabled: signatory, retry: false,
    queryFn: () => api<Envelope<CaseItem[]>>("/api/v1/employers/me/transfer-requests") });

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try {
      const done = await work();
      if (done) { setNotice(done); await qc.invalidateQueries({ queryKey: ["employer-approvals"] }); await qc.invalidateQueries({ queryKey: ["employer-transfers"] }); }
    } catch (cause) { setError(cause); }
  }

  const markExit = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const uan = String(f.get("uan")).trim();
    void run(async () => {
      const token = await stepUp.ask({ action: "mark-exit-employer", resourceId: uan,
        summary: `Mark ${String(f.get("date_of_exit"))} as the date of exit for UAN ${uan} (member ID ${String(f.get("account")).trim()}).` });
      if (!token) return null;
      const r = await command<Envelope<CaseItem>>("POST", `/api/v1/employers/me/members/${encodeURIComponent(uan)}/exits`, {
        account_link_id: String(f.get("account")).trim(), date_of_exit: String(f.get("date_of_exit")), reason: String(f.get("reason")) },
        { stepUpToken: token });
      form.reset();
      return `Exit marked (${r.data.case_id}); it takes effect when the authorised signatory approves it under Approvals.`;
    }); };

  const decide = (c: CaseItem, kind: "exit" | "transfer") => (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    const decision = String(f.get("decision")); const note = String(f.get("note")).trim();
    void run(async () => {
      const action = kind === "exit" ? "approve-exit" : "attest-transfer";
      const summary = kind === "exit"
        ? `${decision === "APPROVE" ? "Approve" : "Reject"} the date of exit ${c.data.date_of_exit} for UAN ${c.subject_ref} (member ID ${c.data.account_link_id}).`
        : `${decision === "ATTEST" ? "Attest" : "Reject"} the transfer of member ID ${c.data.from_account_link_id} to ${c.data.to_account_link_id} for UAN ${c.subject_ref}.`;
      const token = await stepUp.ask({ action, resourceId: c.case_id, resourceVersion: c.version, summary });
      if (!token) return null;
      const path = kind === "exit" ? `/api/v1/employers/me/approvals/${c.case_id}/decisions` : `/api/v1/employers/me/transfer-requests/${c.case_id}/decisions`;
      await command("POST", path, { decision, note }, { stepUpToken: token });
      return `Recorded for ${c.case_id}.`;
    }); };

  const decisionForm = (c: CaseItem, kind: "exit" | "transfer") => (
    <form className="stack" onSubmit={decide(c, kind)}>
      <fieldset className="case-options"><legend>Decision for {c.case_id}</legend>
        <label className="check-row"><input type="radio" name="decision" value={kind === "exit" ? "APPROVE" : "ATTEST"} required />{kind === "exit" ? "Approve" : "Attest"}</label>
        <label className="check-row"><input type="radio" name="decision" value="REJECT" />Reject</label>
      </fieldset>
      <label>Note<textarea name="note" required minLength={5} maxLength={1000} /></label>
      <div className="actions"><button type="submit" className="primary">Record with DSC / e-sign</button></div>
    </form>
  );

  return (
    <section className="stack" aria-labelledby="member-actions-heading">
      <PageHeader id="member-actions-heading" eyebrow="Employer services · members" title="Member exits and transfers"
        description="Mark a member's date of exit; the authorised signatory approves exits and attests members' transfer requests." current="Members" />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}

      <PendingApprovals />
      {!signatory ? (
        <form className="card stack" aria-labelledby="exit-heading" onSubmit={markExit}><h2 id="exit-heading">Mark date of exit</h2>
          <p className="muted small">The exit takes effect only after the authorised signatory approves it (Member › Approvals).</p>
          <div className="form-row">
            <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
            <label>Member ID at this establishment<input name="account" required placeholder="AL-0003" /></label>
            <label>Date of exit<input type="date" name="date_of_exit" required /></label>
            <label>Reason<select name="reason"><option value="CESSATION">Cessation (short service)</option><option value="SUPERANNUATION">Superannuation</option>
              <option value="RETIREMENT">Retirement</option><option value="DEATH_IN_SERVICE">Death while in service</option><option value="PERMANENT_DISABLEMENT">Permanent disablement</option></select></label>
          </div>
          <div className="actions"><button type="submit" className="primary">Mark exit</button></div>
        </form>
      ) : null}

      {signatory ? <>
        <section className="card stack" aria-labelledby="approvals-heading"><h2 id="approvals-heading">Approvals — dates of exit</h2>
          <ProblemMessage error={approvals.error} />
          {approvals.data?.data.length ? approvals.data.data.map((c) => (
            <div key={c.case_id} className="card stack"><p><strong>UAN {c.subject_ref}</strong> · member ID {c.data.account_link_id} · exit {c.data.date_of_exit} · {c.data.reason?.replaceAll("_", " ").toLowerCase()}</p>
              {decisionForm(c, "exit")}</div>)) : <p className="muted">Nothing awaiting approval.</p>}
        </section>
        <section className="card stack" aria-labelledby="transfers-heading"><h2 id="transfers-heading">Transfer claims awaiting attestation</h2>
          <ProblemMessage error={transfers.error} />
          {transfers.data?.data.length ? transfers.data.data.map((c) => (
            <div key={c.case_id} className="card stack"><p><strong>UAN {c.subject_ref}</strong> · from {c.data.from_account_link_id} to {c.data.to_account_link_id}</p>
              {decisionForm(c, "transfer")}</div>)) : <p className="muted">No transfer claims awaiting attestation.</p>}
        </section>
      </> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
