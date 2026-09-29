import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const registrationsPath = "/api/v1/office/establishment-registrations";
const changesPath = "/api/v1/office/establishment-change-requests?state=PENDING";
const text = (form: FormData, key: string) => String(form.get(key) ?? "").trim();
const show = (value: unknown): string => value == null || value === "" ? "—" : typeof value === "boolean" ? value ? "Yes" : "No" : String(value);

interface ScrutinyNote { by_role: string; checks: string[]; note: string; at: string }
interface Registration { request_id: string; establishment_id: string; legal_name: string; registration_number: string;
  stage: string; efile_no: string | null; notes: ScrutinyNote[]; coverage: Record<string, unknown> | null }
interface Documents { establishment: Record<string, unknown>; documents: { type: string; verified_by: string; reference: string }[];
  mock_verification: string; note: string }
interface ChangeRequest { request_id: string; establishment_id: string; legal_name: string; kind: string;
  changes: Record<string, { from: unknown; to: unknown }>; reason: string; state: string }

function Facts({ data }: { data: Record<string, unknown> }) {
  return <dl className="kv">{Object.entries(data).map(([key, value]) => <div key={key} style={{ display: "contents" }}>
    <dt>{key.replaceAll("_", " ")}</dt><dd>{key.endsWith("_paise") && typeof value === "number" ? rupees(value) : show(value)}</dd>
  </div>)}</dl>;
}

export function OlrePage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Documents | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const canView = role === "fo.da_compliance" || role === "fo.apfc";
  const apfc = role === "fo.apfc";
  const registrations = useQuery({ queryKey: ["olre-registrations"], enabled: canView, retry: false,
    queryFn: () => api<Envelope<Registration[]>>(registrationsPath) });
  const changes = useQuery({ queryKey: ["olre-change-requests"], enabled: apfc, retry: false,
    queryFn: () => api<Envelope<ChangeRequest[]>>(changesPath) });
  const loadError = [session.error, registrations.error, changes.error].find(Boolean);

  async function run(work: () => Promise<string | null>) {
    setError(null); setNotice(null);
    try { const result = await work(); if (result) setNotice(result); } catch (cause) { setError(cause); }
  }
  function viewDocuments(requestId: string) {
    void run(async () => {
      setSelectedRequest(requestId); setDocuments(null);
      setDocuments((await api<Envelope<Documents>>(`${registrationsPath}/${encodeURIComponent(requestId)}/documents`)).data);
      return null;
    });
  }
  function submitScrutiny(e: FormEvent<HTMLFormElement>, requestId: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const checks = f.getAll("checks").map(String);
      if (!checks.length) throw new Error("Select at least one scrutiny check.");
      const result = await command<Envelope<Registration>>("POST", `${registrationsPath}/${encodeURIComponent(requestId)}/scrutiny-notes`,
        { checks, note: text(f, "note") });
      form.reset(); await qc.invalidateQueries({ queryKey: ["olre-registrations"] });
      return `Scrutiny recorded in ${result.data.efile_no}.`;
    });
  }
  function decideCoverage(e: FormEvent<HTMLFormElement>, requestId: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(async () => {
      const decision = text(f, "decision"), coverageDate = text(f, "coverage_date");
      if (decision === "COVER" && !coverageDate) throw new Error("Enter a coverage date when covering the establishment.");
      const token = await stepUp.ask({ action: "decide-coverage", resourceId: requestId,
        summary: `${decision === "COVER" ? "Cover" : "Do not cover"} registration ${requestId}.` });
      if (!token) return null;
      await command<Envelope<Registration>>("POST", `${registrationsPath}/${encodeURIComponent(requestId)}/coverage-decisions`,
        { decision, coverage_date: coverageDate || null, coverage_type: text(f, "coverage_type"), reason: text(f, "reason") },
        { stepUpToken: token });
      await qc.invalidateQueries({ queryKey: ["olre-registrations"] });
      return `Coverage decision recorded for ${requestId}.`;
    });
  }
  function decideChange(e: FormEvent<HTMLFormElement>, request: ChangeRequest) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const submitter = (e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value;
    if (decision !== "APPROVE" && decision !== "REJECT") return;
    void run(async () => {
      const token = await stepUp.ask({ action: "decide-establishment-change", resourceId: request.request_id,
        summary: `${decision === "APPROVE" ? "Approve" : "Reject"} change request ${request.request_id} for ${request.legal_name}.` });
      if (!token) return null;
      await command<Envelope<ChangeRequest>>("POST",
        `/api/v1/office/establishments/${encodeURIComponent(request.establishment_id)}/change-requests/${encodeURIComponent(request.request_id)}/decisions`,
        { decision, note: text(f, "note") }, { stepUpToken: token });
      form.reset(); await qc.invalidateQueries({ queryKey: ["olre-change-requests"] });
      return `Change request ${request.request_id} ${decision === "APPROVE" ? "approved" : "rejected"}.`;
    });
  }

  return <section className="stack" aria-labelledby="olre-page-heading">
    <PageHeader id="olre-page-heading" eyebrow="Regional office" title="OLRE and establishment changes" current="OLRE"
      description="Scrutinise new establishment registrations, decide coverage, and review requested changes to establishment records." />
    <ProblemMessage error={error ?? loadError} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}

    <section className="card stack" aria-labelledby="olre-heading"><h2 id="olre-heading">New registrations</h2>
      {registrations.data?.data.length ? <ul className="plain-list">{registrations.data.data.map((registration) => <li key={registration.request_id} className="stack">
        <div><strong>{registration.legal_name}</strong> · {registration.registration_number} · {registration.request_id}
          {" "}<span className="state-pill">{registration.stage.replaceAll("_", " ")}</span></div>
        <Facts data={{ establishment_id: registration.establishment_id, efile_no: registration.efile_no }} />
        {registration.coverage ? <div><h3>Coverage decision</h3><Facts data={registration.coverage} /></div> : null}
        {registration.notes.length ? <div><h3>Scrutiny notes</h3><ul>{registration.notes.map((note, index) => <li key={index}>
          <strong>{note.by_role}</strong> · {note.at}: {note.note} ({note.checks.map((check) => check.replaceAll("_", " ")).join(", ")})
        </li>)}</ul></div> : null}
        <div className="actions"><button type="button" onClick={() => viewDocuments(registration.request_id)}>View documents</button></div>
        {selectedRequest === registration.request_id && documents ? <div className="stack"><h3>Documents for {registration.request_id}</h3>
          <Facts data={documents.establishment} />
          {documents.documents.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Type</th>
            <th scope="col">Verified by</th><th scope="col">Reference</th></tr></thead><tbody>{documents.documents.map((document, index) =>
              <tr key={`${document.type}-${index}`}><td>{document.type}</td><td>{document.verified_by}</td><td>{document.reference}</td></tr>)}</tbody></table></div>
            : <p className="muted">No documents listed.</p>}
          <p className="muted small">{documents.mock_verification} {documents.note}</p>
        </div> : null}
        {role === "fo.da_compliance" && registration.stage !== "COVERAGE_DECIDED" ?
          <form className="stack" aria-label={`Scrutinise registration ${registration.request_id}`} onSubmit={(e) => submitScrutiny(e, registration.request_id)}>
            <h3>Scrutiny</h3><fieldset><legend>Checks completed</legend>
              <label><input type="checkbox" name="checks" value="PAN_VERIFIED" /> PAN verified</label>
              <label><input type="checkbox" name="checks" value="GSTIN_VERIFIED" /> GSTIN verified</label>
              <label><input type="checkbox" name="checks" value="ADDRESS_CHECKED" /> Address checked</label>
              <label><input type="checkbox" name="checks" value="FORM_5A_PARTICULARS_CHECKED" /> Form 5A particulars checked</label>
            </fieldset>
            <label>Note<input name="note" required minLength={10} maxLength={1000} /></label>
            <div className="actions"><button type="submit" className="primary">Record scrutiny</button></div>
          </form> : null}
        {apfc && registration.stage === "SCRUTINISED" ?
          <form className="stack" aria-label={`Decide coverage for ${registration.request_id}`} onSubmit={(e) => decideCoverage(e, registration.request_id)}>
            <h3>Coverage decision</h3><div className="form-row"><label>Decision<select name="decision">
              <option value="COVER">Cover</option><option value="NOT_COVERED">Not covered</option></select></label>
              <label>Coverage date (required when covering)<input name="coverage_date" type="date" /></label>
              <label>Coverage type<select name="coverage_type"><option value="STATUTORY">Statutory</option>
                <option value="VOLUNTARY">Voluntary</option></select></label></div>
            <label>Reason<input name="reason" required minLength={10} maxLength={500} /></label>
            <div className="actions"><button type="submit" className="primary">Record decision</button></div>
          </form> : null}
      </li>)}</ul> : registrations.data ? <p className="muted">No new registrations.</p> : null}
    </section>

    {apfc ? <section className="card stack" aria-labelledby="est-changes-heading"><h2 id="est-changes-heading">Change requests</h2>
      {changes.data?.data.length ? <ul className="plain-list">{changes.data.data.map((request) => <li key={request.request_id} className="stack">
        <div><strong>{request.legal_name}</strong> · {request.request_id} · {request.kind}
          {" "}<span className="state-pill">{request.state}</span></div>
        <p>Reason: {request.reason}</p><ul>{Object.entries(request.changes).map(([field, values]) => <li key={field}>
          {field.replaceAll("_", " ")}: {show(values.from)} → {show(values.to)}</li>)}</ul>
        <form className="stack" aria-label={`Decide change request ${request.request_id}`} onSubmit={(e) => decideChange(e, request)}>
          <label>Decision note<input name="note" required minLength={5} maxLength={500} /></label>
          <div className="actions"><button type="submit" value="APPROVE" className="primary">Approve</button>
            <button type="submit" value="REJECT">Reject</button></div>
        </form>
      </li>)}</ul> : changes.data ? <p className="muted">No pending change requests.</p> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
