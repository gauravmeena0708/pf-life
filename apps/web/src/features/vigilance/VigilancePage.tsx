import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";

const ROLE: Record<string, string> = { "ho.caiu": "CAIU", "ho.cvo": "Chief Vigilance Officer", "zo.vigilance": "Zonal vigilance" };
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import "./vigilance.css";

interface CaseSummary {
  case_id: string; vcn: string; source: string; source_ref: string | null;
  subject_type: string; subject_ref: string; office_id: string; zone_id: string | null;
  state: string; outcome: string | null; pi_due: string | null; opened_at: string | null;
  complainant: { name: string; contact?: string | null } | { masked: true } | null; overdue: boolean;
}
interface CaseDetail extends CaseSummary {
  allegation: string; evidence: { kind: string; ref: string }[];
  findings: { finding: string; report: string; recommendation: string; evidence_examined: string[]; late: boolean; reported_at: string } | null;
  history: { actor: string; action: string; note: string | null; at: string | null }[];
}
interface CaseList { zone_id: string | null; cases: CaseSummary[]; restricted: boolean; note: string }

const decisions: Record<string, { value: string; label: string }[]> = {
  REFERRED: [
    { value: "ASSIGN_INQUIRY", label: "Assign preliminary inquiry" },
    { value: "CLOSED_NO_SUBSTANCE", label: "Close — no substance" },
  ],
  PI_REPORTED: [
    { value: "RETURN_FOR_INQUIRY", label: "Return for further inquiry" },
    { value: "CLOSED_NO_SUBSTANCE", label: "Close — no substance" },
    { value: "MINOR_PENALTY_PROCEEDINGS", label: "Minor penalty proceedings" },
    { value: "MAJOR_PENALTY_PROCEEDINGS", label: "Major penalty proceedings" },
    { value: "REFERRED_TO_CBI", label: "Refer to CBI" },
    { value: "SYSTEM_IMPROVEMENT", label: "System improvement" },
  ],
};
const findings = [
  { value: "SUBSTANTIATED", label: "Substantiated" },
  { value: "PARTLY_SUBSTANTIATED", label: "Partly substantiated" },
  { value: "NOT_SUBSTANTIATED", label: "Not substantiated" },
];

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";
}

function VigilanceWorkspace({ role }: { role: "ho.cvo" | "zo.vigilance" }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [params] = useSearchParams();
  const selected = params.get("case");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const list = useQuery({ queryKey: ["vigilance-cases", role], queryFn: () => api<Envelope<CaseList>>("/api/v1/vigilance/cases"), retry: false });
  const detail = useQuery({ queryKey: ["vigilance-case", selected],
    queryFn: () => api<Envelope<CaseDetail>>(`/api/v1/vigilance/cases/${encodeURIComponent(selected!)}`),
    enabled: !!selected, retry: false });
  const current = detail.data?.data;
  const openDecisions = current ? (decisions[current.state] ?? []) : [];

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!current || busy) return;
    const form = e.currentTarget;
    const values = new FormData(form);
    const read = (name: string) => String(values.get(name) ?? "").trim();
    const isCvo = role === "ho.cvo";
    const decision = read("decision");
    const finding = read("finding");
    if (isCvo && !openDecisions.some((item) => item.value === decision)) return;
    if (!isCvo && (current.state !== "PI_ASSIGNED" || !findings.some((item) => item.value === finding))) return;
    const body = isCvo ? { decision, note: read("note") } : {
      finding, report: read("report"), recommendation: read("recommendation"),
      evidence_examined: values.getAll("evidence_examined").map(String),
    };
    setBusy(true); setError(null); setNotice(null);
    try {
      const token = await stepUp.ask({ action: isCvo ? "decide-vigilance-case" : "report-vigilance-findings",
        resourceId: current.case_id, summary: `${isCvo ? decision : finding} for vigilance case ${current.vcn}.` });
      if (!token) return;
      await command("POST", `/api/v1/vigilance/cases/${encodeURIComponent(current.case_id)}/${isCvo ? "decisions" : "findings"}`,
        body, { stepUpToken: token });
      setNotice(isCvo ? `Decision recorded for ${current.vcn}.` : `Findings reported for ${current.vcn}.`);
      form.reset();
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["vigilance-cases", role] }),
        qc.invalidateQueries({ queryKey: ["vigilance-case", current.case_id] }),
      ]);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <>
    <ProblemMessage error={list.error} />
    <ProblemMessage error={detail.error} />
    <ProblemMessage error={error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {list.isLoading ? <p role="status">Loading cases…</p> : null}
    {list.data && !list.data.data.cases.length ? <p className="card muted">No vigilance cases.</p> : null}
    {list.data && list.data.data.cases.length > 0 ? <section className="card stack" aria-labelledby="vigilance-list-heading">
      <h2 id="vigilance-list-heading">Cases</h2>
      <div className="table-scroll"><table>
        <thead><tr><th scope="col">VCN</th><th scope="col">Subject</th><th scope="col">Office</th><th scope="col">State</th><th scope="col">PI due</th></tr></thead>
        <tbody>{list.data.data.cases.map((item) => <tr key={item.case_id}>
          <td><Link to={`?case=${encodeURIComponent(item.case_id)}`} aria-current={selected === item.case_id ? "true" : undefined}>{item.vcn}</Link></td>
          <td>{item.subject_type} · <code>{item.subject_ref}</code></td>
          <td>{item.office_id}</td>
          <td><span className="state-pill">{statusLabel(item.state, t)}</span></td>
          <td>{dateLabel(item.pi_due)} {item.overdue ? <span className="vigilance-alert-pill">Overdue</span> : null}</td>
        </tr>)}</tbody>
      </table></div>
    </section> : null}
    {selected && detail.isLoading ? <p role="status">Loading case…</p> : null}
    {current ? <article className="card stack vigilance-case" aria-labelledby="vigilance-case-heading">
      <div className="section-heading"><div><p className="eyebrow">Case record</p><h2 id="vigilance-case-heading">{current.vcn}</h2></div>
        <span className="state-pill">{statusLabel(current.state, t)}</span></div>
      <dl className="kv">
        <dt>Subject</dt><dd>{current.subject_type} · <code>{current.subject_ref}</code></dd>
        <dt>Office</dt><dd>{current.office_id}</dd>
        <dt>PI due</dt><dd>{dateLabel(current.pi_due)} {current.overdue ? <span className="vigilance-alert-pill">Overdue</span> : null}</dd>
        <dt>Complainant</dt><dd>{role === "zo.vigilance" && current.complainant ? "Masked — known to the CVO only" : current.complainant && "name" in current.complainant ? <>{current.complainant.name}{current.complainant.contact ? ` · ${current.complainant.contact}` : ""}</> : "Not provided"}</dd>
        {current.outcome ? <><dt>Outcome</dt><dd>{statusLabel(current.outcome, t)}</dd></> : null}
      </dl>
      <section aria-labelledby="vigilance-allegation-heading"><h3 id="vigilance-allegation-heading">Allegation</h3><p className="vigilance-prose">{current.allegation}</p></section>
      <section aria-labelledby="vigilance-evidence-heading"><h3 id="vigilance-evidence-heading">Evidence</h3>
        {current.evidence.length ? <ul className="vigilance-list">{current.evidence.map((item, index) => <li key={`${item.kind}-${item.ref}-${index}`}>{item.kind.replaceAll("_", " ")} · <code>{item.ref}</code></li>)}</ul> : <p className="muted">No evidence references supplied.</p>}
      </section>
      {current.findings ? <section aria-labelledby="vigilance-findings-heading"><h3 id="vigilance-findings-heading">Inquiry findings {current.findings.late ? <span className="vigilance-alert-pill">Late</span> : null}</h3>
        <dl className="kv"><dt>Finding</dt><dd>{statusLabel(current.findings.finding, t)}</dd>
          <dt>Reported</dt><dd>{dateLabel(current.findings.reported_at)}</dd>
          <dt>Report</dt><dd className="vigilance-prose">{current.findings.report}</dd>
          <dt>Recommendation</dt><dd className="vigilance-prose">{current.findings.recommendation}</dd>
          <dt>Evidence examined</dt><dd>{current.findings.evidence_examined.length ? current.findings.evidence_examined.join(", ") : "—"}</dd></dl>
      </section> : null}
      <section aria-labelledby="vigilance-history-heading"><h3 id="vigilance-history-heading">History</h3>
        {current.history.length ? <ol className="vigilance-list">{current.history.map((item, index) => <li key={index}><strong>{statusLabel(item.action, t)}</strong> · {ROLE[item.actor] ?? item.actor} · {dateLabel(item.at)}{item.note ? ` — ${item.note}` : ""}</li>)}</ol> : <p className="muted">No history recorded.</p>}
      </section>
      {role === "ho.cvo" && openDecisions.length ? <form className="stack" aria-label="Record vigilance decision" onSubmit={(e) => void submit(e)}>
        <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>CVO decision</legend>
          <label>Decision<select name="decision" required defaultValue=""><option value="">Choose decision</option>{openDecisions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label>Decision note<textarea name="note" required minLength={10} maxLength={2000} /></label>
          <div className="actions"><button type="submit" className="primary">Record decision</button></div>
        </fieldset>
      </form> : null}
      {role === "zo.vigilance" && current.state === "PI_ASSIGNED" ? <form className="stack" aria-label="Report vigilance findings" onSubmit={(e) => void submit(e)}>
        <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>Preliminary inquiry</legend>
          <fieldset className="case-options"><legend>Finding</legend>{findings.map((item) => <label className="check-row" key={item.value}>
            <input type="radio" name="finding" value={item.value} required />{item.label}</label>)}</fieldset>
          <label>Report<textarea name="report" required minLength={50} maxLength={8000} /></label>
          <label>Recommendation<textarea name="recommendation" required minLength={10} maxLength={2000} /></label>
          <fieldset className="case-options"><legend>Evidence examined</legend>{current.evidence.length ? current.evidence.map((item, index) => <label className="check-row" key={`${item.ref}-${index}`}>
            <input type="checkbox" name="evidence_examined" value={item.ref} />{item.kind.replaceAll("_", " ")} · {item.ref}</label>) : <p className="muted">No evidence references supplied.</p>}</fieldset>
          <div className="actions"><button type="submit" className="primary">Report findings</button></div>
        </fieldset>
      </form> : null}
      {role === "ho.cvo" && !openDecisions.length ? <p className="muted">No decision is open for this state. Awaiting the zonal inquiry where applicable.</p> : null}
    </article> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </>;
}

export function VigilancePage() {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  return <section className="stack vigilance-page" aria-labelledby="vigilance-heading">
    <PageHeader id="vigilance-heading" eyebrow="Vigilance" title="Vigilance cases"
      description="Restricted: every read of a vigilance case is recorded in the audit log." current="Vigilance cases" />
    <ProblemMessage error={session.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {role === "ho.cvo" || role === "zo.vigilance" ? <VigilanceWorkspace role={role} /> : session.data ?
      <p className="pending-notice">This screen is for the Chief Vigilance Officer and zonal vigilance.</p> : null}
  </section>;
}
