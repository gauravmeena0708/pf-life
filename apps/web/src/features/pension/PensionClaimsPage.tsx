import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog, type StepUpRequest } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface PensionClaim {
  claim_id: string;
  uan: string;
  name: string;
  state: string;
  pension_from: string;
  service_months: number;
  aggregated: { source: string; cert_id: string | null; service_months: number; note: string }[];
  pensionable_salary_paise: number;
  ids: { ids_id: string; service_months: number; pensionable_salary_paise: number; note: string } | null;
  worksheet: { worksheet_id: string; service_months: number; monthly_paise: number; working: string; rule_version: string; age_at_start: number } | null;
  ppo_id: string | null;
  arrears: { months: string[]; monthly_paise: number; amount_paise: number } | null;
  history: { state: string; role: string; note: string; at: string }[];
  next_step: string | null;
}

type Decision = "APPROVE" | "RETURN";
type SurrenderDecision = "CANCEL" | "RETURN";

function label(value: string) {
  return value.replace(/_/g, " ").toLowerCase();
}

export function PensionClaimsPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  const claims = useQuery({
    queryKey: ["pension-claims"],
    queryFn: () => api<Envelope<PensionClaim[]>>("/api/v1/office/pension-claims"),
    retry: false,
  });

  async function runCommand(key: string, message: string, path: string, body?: unknown, request?: StepUpRequest) {
    setError(null);
    setNotice(null);
    setBusy(key);
    try {
      const token = request ? await stepUp.ask(request) : undefined;
      if (request && !token) return false;
      await command("POST", path, body, token ? { stepUpToken: token } : undefined);
      setNotice(message);
      await qc.invalidateQueries({ queryKey: ["pension-claims"] });
      return true;
    } catch (cause) {
      setError(cause);
      return false;
    } finally {
      setBusy(null);
    }
  }

  function promptNote(action: string, id: string) {
    const answer = window.prompt(`${action} ${id}: enter a note of at least 10 characters:`);
    if (answer === null) return null;
    const note = answer.trim();
    if (note.length < 10) {
      setError(new Error("Enter a note of at least 10 characters."));
      return null;
    }
    return note;
  }

  function submitIds(event: FormEvent<HTMLFormElement>, claim: PensionClaim) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const serviceMonths = Number(form.get("service_months"));
    const salaryRupees = Number(form.get("pensionable_salary_rupees"));
    const note = String(form.get("note") ?? "").trim();
    if (!Number.isInteger(serviceMonths) || serviceMonths < 0 || !Number.isFinite(salaryRupees) || salaryRupees < 0 || note.length < 10) {
      setError(new Error("Enter valid service months, pensionable salary and a note of at least 10 characters."));
      return;
    }
    void runCommand(claim.claim_id, `Input Data Sheet prepared for ${claim.claim_id}.`,
      `/api/v1/office/pension-claims/${encodeURIComponent(claim.claim_id)}/input-data-sheets`,
      { service_months: serviceMonths, pensionable_salary_paise: Math.round(salaryRupees * 100), note });
  }

  function submitAggregation(event: FormEvent<HTMLFormElement>, claim: PensionClaim) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const source = String(form.get("source"));
    const certId = String(form.get("cert_id") ?? "").trim();
    const serviceMonths = Number(form.get("service_months"));
    const note = String(form.get("note") ?? "").trim();
    if (!Number.isInteger(serviceMonths) || serviceMonths < 1 || note.length < 10) {
      setError(new Error("Enter whole service months and a note of at least 10 characters."));
      return;
    }
    void runCommand(claim.claim_id, `Past service added to ${claim.claim_id}.`, "/api/v1/office/pensions/service-aggregations",
      { claim_id: claim.claim_id, source, cert_id: certId || null, service_months: serviceMonths, note },
      { action: "aggregate-service", resourceId: claim.claim_id, summary: `Add ${serviceMonths} months of ${label(source)} to pension claim ${claim.claim_id}.` })
      .then((saved) => { if (saved) element.reset(); });
  }

  function decideIds(claim: PensionClaim, decision: Decision) {
    if (!claim.ids) return;
    const note = promptNote(decision === "APPROVE" ? "Approve Input Data Sheet" : "Return Input Data Sheet", claim.claim_id);
    if (!note) return;
    const idsId = claim.ids.ids_id;
    void runCommand(claim.claim_id, `${decision === "APPROVE" ? "Approved" : "Returned"} Input Data Sheet ${idsId}.`,
      `/api/v1/office/pension-claims/${encodeURIComponent(claim.claim_id)}/input-data-sheets/${encodeURIComponent(idsId)}/approvals`,
      { decision, note }, { action: "approve-ids", resourceId: idsId, summary: `${decision === "APPROVE" ? "Approve" : "Return"} Input Data Sheet ${idsId} for pension claim ${claim.claim_id}.` });
  }

  function decideWorksheet(claim: PensionClaim, decision: Decision) {
    if (!claim.worksheet) return;
    const note = promptNote(decision === "APPROVE" ? "Approve worksheet" : "Return worksheet", claim.claim_id);
    if (!note) return;
    const worksheetId = claim.worksheet.worksheet_id;
    void runCommand(claim.claim_id, `${decision === "APPROVE" ? "Approved" : "Returned"} worksheet ${worksheetId}.`,
      `/api/v1/office/pensions/worksheets/${encodeURIComponent(worksheetId)}/approvals`,
      { decision, note }, { action: "approve-worksheet", resourceId: worksheetId, summary: `${decision === "APPROVE" ? "Approve" : "Return"} worksheet ${worksheetId} for pension claim ${claim.claim_id}.` });
  }

  function claimActions(claim: PensionClaim) {
    const disabled = busy !== null;
    const id = claim.claim_id;
    if (role === "fo.da_accounts" && (claim.state === "SUBMITTED" || claim.state === "RETURNED")) {
      return <form className="stack" onSubmit={(event) => submitIds(event, claim)}>
        <h3>Prepare Input Data Sheet</h3>
        <div className="form-row">
          <label>Service months<input name="service_months" type="number" min={0} max={600} step={1} defaultValue={claim.service_months} required /></label>
          <label>Pensionable salary (rupees)<input name="pensionable_salary_rupees" type="number" min={0} step="0.01" defaultValue={claim.pensionable_salary_paise / 100} required /></label>
        </div>
        <label>Note<textarea name="note" minLength={10} maxLength={1000} required /></label>
        <div className="actions"><button type="submit" className="primary" disabled={disabled}>Prepare sheet</button></div>
      </form>;
    }
    if (role === "fo.ao" && claim.state === "IDS_PREPARED" && claim.ids) {
      return <div className="actions"><button type="button" className="primary" disabled={disabled} onClick={() => decideIds(claim, "APPROVE")}>Approve</button>
        <button type="button" disabled={disabled} onClick={() => decideIds(claim, "RETURN")}>Return</button></div>;
    }
    if (role === "fo.da_pension" && claim.state === "IDS_APPROVED") {
      return <div className="stack">
        <div className="actions"><button type="button" className="primary" disabled={disabled} onClick={() => void runCommand(id, `Worksheet generated for ${id}.`,
          "/api/v1/office/pensions/worksheets", { claim_id: id })}>Generate worksheet</button></div>
        <form className="stack" onSubmit={(event) => submitAggregation(event, claim)}>
          <h3>Add past service</h3>
          <div className="form-row">
            <label>Source<select name="source" defaultValue="SCHEME_CERTIFICATE"><option value="SCHEME_CERTIFICATE">Scheme certificate</option>
              <option value="UNTRANSFERRED_SERVICE">Untransferred service</option></select></label>
            <label>Certificate number (optional)<input name="cert_id" /></label>
            <label>Service months<input name="service_months" type="number" min={1} max={480} step={1} required /></label>
          </div>
          <label>Note<textarea name="note" minLength={10} maxLength={500} required /></label>
          <div className="actions"><button type="submit" disabled={disabled}>Add past service</button></div>
        </form>
      </div>;
    }
    if (role === "fo.apfc_pension" && claim.state === "WORKSHEET_PREPARED" && claim.worksheet) {
      return <div className="actions"><button type="button" className="primary" disabled={disabled} onClick={() => decideWorksheet(claim, "APPROVE")}>Approve</button>
        <button type="button" disabled={disabled} onClick={() => decideWorksheet(claim, "RETURN")}>Return</button></div>;
    }
    if (role === "fo.da_pension" && claim.state === "WORKSHEET_APPROVED") {
      return <button type="button" className="primary" disabled={disabled} onClick={() => void runCommand(id, `PPO issued for ${id}.`,
        "/api/v1/office/pensions/ppo-issuances", { claim_id: id },
        { action: "issue-ppo", resourceId: id, summary: `Issue the PPO for pension claim ${id} (${claim.name}).` })}>Issue PPO</button>;
    }
    if (role === "fo.da_pension" && claim.state === "PPO_ISSUED" && claim.ppo_id) {
      return <button type="button" className="primary" disabled={disabled} onClick={() => void runCommand(id, `Initial arrear proposed for ${claim.ppo_id}.`,
        `/api/v1/office/pensions/ppos/${encodeURIComponent(claim.ppo_id!)}/initial-arrears`,
        { action: "PROPOSE", note: "Initial arrear proposed" })}>Propose initial arrear</button>;
    }
    if (role === "fo.ss_pension" && claim.state === "ARREAR_PROPOSED" && claim.ppo_id) {
      return <button type="button" className="primary" disabled={disabled} onClick={() => {
        const note = promptNote("Check arrear", claim.ppo_id!);
        if (note) void runCommand(id, `Initial arrear checked for ${claim.ppo_id}.`,
          `/api/v1/office/pensions/ppos/${encodeURIComponent(claim.ppo_id!)}/initial-arrears`, { action: "CHECK", note });
      }}>Check arrear</button>;
    }
    if (role === "fo.apfc_pension" && claim.state === "ARREAR_CHECKED" && claim.ppo_id && claim.arrears) {
      return <button type="button" className="primary" disabled={disabled} onClick={() => {
        const note = promptNote("E-sign PPO", claim.ppo_id!);
        if (note) void runCommand(id, `PPO ${claim.ppo_id} signed.`,
          `/api/v1/office/pensions/ppos/${encodeURIComponent(claim.ppo_id!)}/e-signatures`, { decision: "APPROVE", note },
          { action: "esign-ppo", resourceId: claim.ppo_id!, amountPaise: claim.arrears!.amount_paise,
            summary: `E-sign PPO ${claim.ppo_id} for ${claim.name}: monthly pension ${rupees(claim.arrears!.monthly_paise)} and initial arrear ${rupees(claim.arrears!.amount_paise)}.` });
      }}>E-sign PPO</button>;
    }
    if (role === "fo.da_pension" && claim.state === "PPO_SIGNED" && claim.ppo_id) {
      return <button type="button" className="primary" disabled={disabled} onClick={() => void runCommand(id, `PPO ${claim.ppo_id} dispatched.`,
        `/api/v1/office/pensions/ppos/${encodeURIComponent(claim.ppo_id!)}/dispatches`)}>Dispatch PPO</button>;
    }
    return null;
  }

  function submitTransfer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const ppoId = String(form.get("ppo_id") ?? "").trim();
    const monthlyRupees = Number(form.get("monthly_rupees"));
    if (!Number.isFinite(monthlyRupees) || monthlyRupees <= 0) {
      setError(new Error("Enter a valid monthly pension."));
      return;
    }
    void runCommand("transfer", `Transfer in recorded for PPO ${ppoId}.`, "/api/v1/office/pensions/transfers-in", {
      ppo_id: ppoId,
      name: String(form.get("name") ?? "").trim(),
      uan: String(form.get("uan") ?? "").trim(),
      date_of_birth: String(form.get("date_of_birth") ?? ""),
      pension_start: String(form.get("pension_start") ?? ""),
      monthly_paise: Math.round(monthlyRupees * 100),
      from_office: String(form.get("from_office") ?? "").trim(),
      with_ppo: form.has("with_ppo"),
    }).then((saved) => { if (saved) element.reset(); });
  }

  function submitSurrender(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const cert = String(form.get("cert_id") ?? "").trim();
    const note = String(form.get("note") ?? "").trim();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value as SurrenderDecision | undefined;
    if (!cert || note.length < 10 || (decision !== "CANCEL" && decision !== "RETURN")) {
      setError(new Error("Enter a certificate number, a note of at least 10 characters and a decision."));
      return;
    }
    void runCommand("surrender", `Scheme certificate ${cert} ${decision === "CANCEL" ? "cancelled" : "returned"}.`,
      `/api/v1/office/pensions/scheme-certificates/${encodeURIComponent(cert)}/surrender-adjudications`, { decision, note },
      { action: "adjudicate-surrender", resourceId: cert, summary: `${decision === "CANCEL" ? "Cancel" : "Return"} scheme certificate ${cert}.` })
      .then((saved) => { if (saved) element.reset(); });
  }

  return <div className="stack">
    <PageHeader id="pension-claims-page-heading" eyebrow="Pension administration" title="Pension claims (Form 10D)"
      description="Review pension claims and record each step in the approval process." current="Pension claims" />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    <ProblemMessage error={error} />
    <ProblemMessage error={session.error} />
    <section className="card stack" aria-labelledby="claims-heading">
      <h2 id="claims-heading">Pension claims</h2>
      <ProblemMessage error={claims.error} />
      {claims.isLoading ? <p role="status">Loading pension claims…</p> : null}
      {claims.data?.data.length === 0 ? <p className="muted small">No pension claims.</p> : null}
      {claims.data?.data.length ? <div className="table-scroll"><table>
        <thead><tr><th scope="col">Claim ID</th><th scope="col">Pensioner</th><th scope="col">Pension from</th>
          <th scope="col">State</th><th scope="col">Next step</th></tr></thead>
        <tbody>{claims.data.data.map((claim) => <tr key={claim.claim_id}>
          <td>{claim.claim_id}</td>
          <td><strong>{claim.name}</strong><br /><span className="muted small">UAN {claim.uan}</span></td>
          <td>{claim.pension_from}</td>
          <td><span className="state-pill">{label(claim.state)}</span></td>
          <td><div className="stack">
            <span>{claim.next_step ?? "—"}</span>
            <details><summary>Claim details and history</summary>
              <div className="stack">
                <dl className="kv">
                  <div><dt>Service months</dt><dd>{claim.service_months}</dd></div>
                  <div><dt>Pensionable salary</dt><dd>{rupees(claim.pensionable_salary_paise)}</dd></div>
                  {claim.ppo_id ? <div><dt>PPO</dt><dd>{claim.ppo_id}</dd></div> : null}
                </dl>
                {claim.ids ? <><h3>Input Data Sheet</h3><dl className="kv">
                  <div><dt>Sheet</dt><dd>{claim.ids.ids_id}</dd></div>
                  <div><dt>Service months</dt><dd>{claim.ids.service_months}</dd></div>
                  <div><dt>Pensionable salary</dt><dd>{rupees(claim.ids.pensionable_salary_paise)}</dd></div>
                  <div><dt>Note</dt><dd>{claim.ids.note}</dd></div>
                </dl></> : null}
                {claim.aggregated.length ? <><h3>Past service</h3><ul>{claim.aggregated.map((item, index) => <li key={`${item.source}-${item.cert_id ?? index}`}>
                  {label(item.source)}: {item.service_months} months{item.cert_id ? `, certificate ${item.cert_id}` : ""}. {item.note}
                </li>)}</ul></> : null}
                {claim.worksheet ? <><h3>Worksheet</h3><dl className="kv">
                  <div><dt>Worksheet</dt><dd>{claim.worksheet.worksheet_id}</dd></div>
                  <div><dt>Service months</dt><dd>{claim.worksheet.service_months}</dd></div>
                  <div><dt>Monthly pension</dt><dd>{rupees(claim.worksheet.monthly_paise)}</dd></div>
                  <div><dt>Working</dt><dd>{claim.worksheet.working}</dd></div>
                  <div><dt>Rule version</dt><dd>{claim.worksheet.rule_version}</dd></div>
                  <div><dt>Age at start</dt><dd>{claim.worksheet.age_at_start}</dd></div>
                </dl></> : null}
                {claim.arrears ? <><h3>Initial arrear</h3><dl className="kv">
                  <div><dt>Months</dt><dd>{claim.arrears.months.join(", ") || "None"}</dd></div>
                  <div><dt>Monthly pension</dt><dd>{rupees(claim.arrears.monthly_paise)}</dd></div>
                  <div><dt>Arrear amount</dt><dd>{rupees(claim.arrears.amount_paise)}</dd></div>
                </dl></> : null}
                <h3>History</h3>
                {claim.history.length ? <ol>{claim.history.map((entry, index) => <li key={`${entry.at}-${index}`}>
                  {entry.at} — {entry.role} — {label(entry.state)}: {entry.note}
                </li>)}</ol> : <p className="muted small">No history recorded.</p>}
              </div>
            </details>
            {claimActions(claim)}
          </div></td>
        </tr>)}</tbody>
      </table></div> : null}
    </section>
    {role === "fo.da_pension" ? <>
      <section className="card stack" aria-labelledby="transfer-in-heading">
        <h2 id="transfer-in-heading">Transfer in</h2>
        <form className="stack" onSubmit={submitTransfer}>
          <div className="form-row">
            <label>PPO number<input name="ppo_id" minLength={3} maxLength={40} required /></label>
            <label>Name<input name="name" minLength={2} maxLength={120} required /></label>
            <label>UAN<input name="uan" inputMode="numeric" pattern="[0-9]{12}" required /></label>
          </div>
          <div className="form-row">
            <label>Date of birth<input name="date_of_birth" type="date" required /></label>
            <label>Pension start<input name="pension_start" type="date" required /></label>
            <label>Monthly pension (rupees)<input name="monthly_rupees" type="number" min="0.01" step="0.01" required /></label>
            <label>From office<input name="from_office" minLength={3} maxLength={40} required /></label>
          </div>
          <label className="check-row"><input name="with_ppo" type="checkbox" />With PPO</label>
          <div className="actions"><button type="submit" className="primary" disabled={busy !== null}>Record transfer in</button></div>
        </form>
      </section>
      <section className="card stack" aria-labelledby="surrender-heading">
        <h2 id="surrender-heading">Scheme certificate surrender</h2>
        <form className="stack" onSubmit={submitSurrender}>
          <div className="form-row"><label>Certificate number<input name="cert_id" required /></label></div>
          <label>Decision note<textarea name="note" minLength={10} maxLength={1000} required /></label>
          <div className="actions">
            <button type="submit" name="decision" value="CANCEL" className="primary" disabled={busy !== null}>Cancel the certificate</button>
            <button type="submit" name="decision" value="RETURN" disabled={busy !== null}>Return it to the member</button>
          </div>
        </form>
      </section>
    </> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </div>;
}
