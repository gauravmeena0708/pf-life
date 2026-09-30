import { statusLabel } from "../statusLabel";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getMyPermissions, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { PendingApprovals } from "./SignaturePanels";
import { MemberLocations } from "./MemberLocations";
import { HigherPensionValidations } from "./HigherPensionValidations";

interface CaseItem { case_id: string; subject_ref: string; state: string; version: number; data: Record<string, string> }
interface ClaimAttestation {
  claim_id: string; uan: string; account_link_id: string; claim_type: string; form_type: string;
  amount_paise: number; version: number; summary: string; filed_at: string; why: string;
}
interface BulkExitResult {
  lines: number; accepted: number;
  results: { line: number; status: "ACCEPTED" | "ERROR"; case_id?: string; uan?: string; error?: string }[];
}

function ExitFields() {
  return <div className="form-row">
    <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label>
    <label>Member ID at this establishment<input name="account" required placeholder="AL-0003" /></label>
    <label>Date of exit<input type="date" name="date_of_exit" required /></label>
    <label>Reason<select name="reason"><option value="CESSATION">Cessation (short service)</option><option value="SUPERANNUATION">Superannuation</option>
      <option value="RETIREMENT">Retirement</option><option value="DEATH_IN_SERVICE">Death while in service</option><option value="PERMANENT_DISABLEMENT">Permanent disablement</option></select></label>
  </div>;
}

/** Member › Member Profile (mark exit), Member › Approvals (the signatory approves exits) and
 * Online Services › Transfer Claims (attest a member's Form 13 transfer). */
export function MemberActionsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState<BulkExitResult | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  useQuery({ queryKey: ["my-permissions"], queryFn: getMyPermissions, retry: false });
  const role = session.data?.stakeholder;
  const signatory = role === "employer.signatory";
  const canExit = role === "employer.operator" || role === "employer.owner";
  const canViewClaims = signatory || role === "employer.owner";
  const disabled = busy || !!stepUp.request;
  const establishment = useQuery({ queryKey: ["member-actions-establishment"], enabled: canExit, retry: false,
    queryFn: () => api<Envelope<{ establishment_id: string }>>("/api/v1/employers/me") });
  const approvals = useQuery({ queryKey: ["employer-approvals"], enabled: signatory, retry: false,
    queryFn: () => api<Envelope<CaseItem[]>>("/api/v1/employers/me/approvals") });
  const transfers = useQuery({ queryKey: ["employer-transfers"], enabled: signatory, retry: false,
    queryFn: () => api<Envelope<CaseItem[]>>("/api/v1/employers/me/transfer-requests") });
  const claimAttestations = useQuery({ queryKey: ["employer-claim-attestations"], enabled: canViewClaims, retry: false,
    queryFn: () => api<Envelope<ClaimAttestation[]>>("/api/v1/employers/me/claim-attestations") });

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null); setBusy(true);
    try {
      const done = await work();
      if (done) { setNotice(done); await Promise.all([
        qc.invalidateQueries({ queryKey: ["employer-approvals"] }), qc.invalidateQueries({ queryKey: ["employer-transfers"] }),
        qc.invalidateQueries({ queryKey: ["employer-claim-attestations"] }), qc.invalidateQueries({ queryKey: ["employer-pending-approvals"] }),
      ]); }
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  const markExit = (e: FormEvent<HTMLFormElement>, correction = false) => { e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const uan = String(f.get("uan")).trim();
    void run(async () => {
      if (!canExit) return null;
      const correctionNote = String(f.get("correction_note") ?? "").trim();
      if (correction && correctionNote.length < 10) throw new Error("Enter a correction note of at least 10 characters.");
      const token = await stepUp.ask({ action: correction ? "correct-exit-employer" : "mark-exit-employer", resourceId: uan,
        summary: `${correction ? "Correct" : "Mark"} ${String(f.get("date_of_exit"))} as the date of exit for UAN ${uan} (member ID ${String(f.get("account")).trim()}).` });
      if (!token) return null;
      const r = await command<Envelope<CaseItem>>("POST", `/api/v1/employers/me/members/${encodeURIComponent(uan)}/${correction ? "exit-corrections" : "exits"}`, {
        account_link_id: String(f.get("account")).trim(), date_of_exit: String(f.get("date_of_exit")), reason: String(f.get("reason")),
        ...(correction ? { correction_note: correctionNote } : {}) },
        { stepUpToken: token });
      form.reset();
      return `${correction ? "Exit correction submitted" : "Exit marked"} (${r.data.case_id}); it takes effect when the authorised signatory approves it under Approvals.`;
    }); };

  function uploadExits(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    const content = String(f.get("content") ?? "");
    setBulkResult(null);
    void run(async () => {
      const establishmentId = establishment.data?.data.establishment_id;
      if (!canExit || !establishmentId) throw new Error("Wait for establishment details to load.");
      if (!content.trim()) throw new Error("Enter CSV content for the exit upload.");
      const token = await stepUp.ask({ action: "mark-exit-bulk", resourceId: establishmentId,
        summary: `Upload bulk member exits for establishment ${establishmentId}. Accepted exits require signatory approval.` });
      if (!token) return null;
      const r = await command<Envelope<BulkExitResult>>("POST", "/api/v1/employers/me/members/exit-bulk-uploads", { content }, { stepUpToken: token });
      setBulkResult(r.data);
      return `${r.data.accepted} of ${r.data.lines} exit lines accepted. Review the results below.`;
    });
  }

  function decideClaim(e: FormEvent<HTMLFormElement>, item: ClaimAttestation) {
    e.preventDefault(); const f = new FormData(e.currentTarget);
    const decision = String(f.get("decision")); const note = String(f.get("note") ?? "").trim();
    void run(async () => {
      if (!signatory) return null;
      if (decision !== "ATTEST" && decision !== "REJECT") throw new Error("Choose whether to attest or reject the claim.");
      if (note.length < 5) throw new Error("Enter a decision note of at least 5 characters.");
      const token = await stepUp.ask({ action: "attest-claim", resourceId: item.claim_id, resourceVersion: item.version,
        summary: `${decision === "ATTEST" ? "Attest" : "Reject"} claim ${item.claim_id} for UAN ${item.uan} (${rupees(item.amount_paise)}). ${item.summary}` });
      if (!token) return null;
      await command("POST", `/api/v1/employers/me/claim-attestations/${encodeURIComponent(item.claim_id)}/decisions`, { decision, note }, { stepUpToken: token });
      return `Claim ${item.claim_id} ${decision === "ATTEST" ? "attested" : "rejected"}.`;
    });
  }

  const decide = (c: CaseItem, kind: "exit" | "transfer") => (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const f = new FormData(e.currentTarget);
    const decision = String(f.get("decision")); const note = String(f.get("note")).trim();
    void run(async () => {
      const action = kind === "exit" ? "approve-exit" : "attest-transfer";
      const summary = kind === "exit"
        ? `${decision === "APPROVE" ? "Approve" : "Reject"} ${c.state === "CORRECTION_MARKED" ? "the exit correction to" : "the date of exit"} ${c.data.date_of_exit} for UAN ${c.subject_ref} (member ID ${c.data.account_link_id}).`
        : `${decision === "ATTEST" ? "Attest" : "Reject"} the transfer of member ID ${c.data.from_account_link_id} to ${c.data.to_account_link_id} for UAN ${c.subject_ref}.`;
      const token = await stepUp.ask({ action, resourceId: c.case_id, resourceVersion: c.version, summary });
      if (!token) return null;
      const path = kind === "exit" ? `/api/v1/employers/me/approvals/${c.case_id}/decisions` : `/api/v1/employers/me/transfer-requests/${c.case_id}/decisions`;
      await command("POST", path, { decision, note }, { stepUpToken: token });
      return `Recorded for ${c.case_id}.`;
    }); };

  const decisionForm = (c: CaseItem, kind: "exit" | "transfer") => (
    <form className="stack" onSubmit={decide(c, kind)}>
      <fieldset className="case-options" disabled={disabled}><legend>Decision for {c.case_id}</legend>
        <label className="check-row"><input type="radio" name="decision" value={kind === "exit" ? "APPROVE" : "ATTEST"} required />{kind === "exit" ? "Approve" : "Attest"}</label>
        <label className="check-row"><input type="radio" name="decision" value="REJECT" />Reject</label>
      </fieldset>
      <label>Note<textarea name="note" required minLength={5} maxLength={1000} disabled={disabled} /></label>
      <div className="actions"><button type="submit" className="primary" disabled={disabled}>Record with DSC / e-sign</button></div>
    </form>
  );

  return (
    <section className="stack" aria-labelledby="member-actions-heading">
      <PageHeader id="member-actions-heading" eyebrow="Employer services · members" title="Member exits, transfers and claim attestations"
        description="Mark or correct exits, upload bulk exits, and review requests awaiting signatory approval." current="Members" />
      <ProblemMessage error={error ?? session.error ?? establishment.error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {session.isLoading ? <p role="status">Loading employer role…</p> : null}

      {role === "employer.operator" || role === "employer.owner" ? <MemberLocations canMap={role === "employer.operator"} /> : null}
      {signatory || canExit ? <PendingApprovals /> : null}
      {canExit ? <>
        <form className="card stack" aria-labelledby="exit-heading" onSubmit={(e) => markExit(e)}><h2 id="exit-heading">Mark date of exit</h2>
          <p className="muted small">The exit takes effect only after the authorised signatory approves it (Member › Approvals).</p>
          <fieldset disabled={disabled}><legend>Exit details</legend><ExitFields /></fieldset>
          <div className="actions"><button type="submit" className="primary" disabled={disabled}>Mark exit</button></div>
        </form>
        <form className="card stack" aria-labelledby="exit-correction-heading" onSubmit={(e) => markExit(e, true)}><h2 id="exit-correction-heading">Exit correction</h2>
          <p className="muted">Correct an existing date of exit. The authorised signatory approves the correction under Member › Approvals.</p>
          <fieldset disabled={disabled} className="stack"><legend>Corrected exit details</legend><ExitFields />
            <label>Correction note<textarea name="correction_note" required minLength={10} maxLength={1000} /></label>
          </fieldset>
          <div className="actions"><button type="submit" className="primary" disabled={disabled}>Submit exit correction</button></div>
        </form>
        <form className="card stack" aria-labelledby="exit-bulk-heading" onSubmit={uploadExits}><h2 id="exit-bulk-heading">Exit bulk upload</h2>
          <p id="exit-bulk-help" className="muted">CSV columns: uan,account_link_id,date_of_exit,reason. The header is optional; dates must use YYYY-MM-DD.
            Reasons: CESSATION, SUPERANNUATION, RETIREMENT, DEATH_IN_SERVICE or PERMANENT_DISABLEMENT. Accepted lines await signatory approval.</p>
          <label>CSV content<textarea name="content" required rows={8} disabled={disabled} aria-describedby="exit-bulk-help"
            placeholder="uan,account_link_id,date_of_exit,reason" /></label>
          <div className="actions"><button type="submit" className="primary" disabled={disabled || !establishment.data}>Upload exits with one-time code</button></div>
          {establishment.isLoading ? <p role="status">Loading establishment details…</p> : null}
          {bulkResult ? <div className="stack"><p role="status">Lines: {bulkResult.lines} · Accepted: {bulkResult.accepted}</p>
            <div className="table-scroll"><table><thead><tr><th scope="col">Line</th><th scope="col">Status</th>
              <th scope="col">UAN</th><th scope="col">Case</th><th scope="col">Error</th></tr></thead>
              <tbody>{bulkResult.results.map((item) => <tr key={item.line}><th scope="row">{item.line}</th><td>{statusLabel(item.status, t)}</td>
                <td>{item.uan ?? "—"}</td><td>{item.case_id ?? "—"}</td><td>{item.error ?? "—"}</td></tr>)}</tbody>
            </table></div>
          </div> : null}
        </form>
      </> : null}

      {canViewClaims ? <section className="card stack" aria-labelledby="claim-attestations-heading"><h2 id="claim-attestations-heading">Claim attestations</h2>
        <ProblemMessage error={claimAttestations.error} />
        {claimAttestations.isLoading ? <p role="status">Loading claim attestations…</p> : null}
        {!signatory ? <p className="muted">Only the authorised signatory can attest or reject a claim.</p> : null}
        {claimAttestations.data?.data.length ? claimAttestations.data.data.map((item) => <article key={item.claim_id} className="card stack">
          <h3>Claim <code>{item.claim_id}</code> · UAN {item.uan}</h3>
          <dl className="kv"><dt>Member ID</dt><dd>{item.account_link_id}</dd><dt>Claim type</dt><dd>{item.form_type} · {item.claim_type}</dd>
            <dt>Amount</dt><dd>{rupees(item.amount_paise)}</dd><dt>Filed</dt><dd>{item.filed_at}</dd></dl>
          <p>{item.summary}</p><p className="pending-notice">{item.why}</p>
          {signatory ? <form className="stack" aria-label={`Decide claim ${item.claim_id}`} onSubmit={(e) => decideClaim(e, item)}>
            <label>Decision<select name="decision" required disabled={disabled}><option value="">Choose decision</option>
              <option value="ATTEST">Attest</option><option value="REJECT">Reject</option></select></label>
            <label>Decision note<textarea name="note" required minLength={5} maxLength={1000} disabled={disabled} /></label>
            <div className="actions"><button type="submit" className="primary" disabled={disabled}>Record claim decision with DSC / e-sign</button></div>
          </form> : null}
        </article>) : claimAttestations.data ? <p className="muted">No claims awaiting attestation.</p> : null}
      </section> : null}

      {signatory ? <>
        <HigherPensionValidations />
        <section className="card stack" aria-labelledby="approvals-heading"><h2 id="approvals-heading">Approvals — dates of exit</h2>
          <ProblemMessage error={approvals.error} />
          {approvals.isLoading ? <p role="status">Loading exit approvals…</p> : null}
          {approvals.data?.data.length ? approvals.data.data.map((c) => (
            <div key={c.case_id} className="card stack"><h3>{c.state === "CORRECTION_MARKED" ? "Exit correction" : "Date of exit"}</h3>
              <p><strong>UAN {c.subject_ref}</strong> · member ID {c.data.account_link_id} · exit {c.data.date_of_exit} · {c.data.reason?.replaceAll("_", " ").toLowerCase()}</p>
              {c.data.correction_note ? <p><strong>Correction note:</strong> {c.data.correction_note}</p> : null}
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
