import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const base = "/api/v1/office/compliance";
type CaseKind = "NON_FILING" | "NON_PAYMENT" | "LATE_PAYMENT_DAMAGES" | "OTHER";
const kindLabels: Record<CaseKind, string> = {
  NON_FILING: "Returns not filed", NON_PAYMENT: "Dues not paid",
  LATE_PAYMENT_DAMAGES: "Damages for late payment", OTHER: "Other",
};
interface Defaulter {
  establishment_id: string; non_filing_months: string[]; non_payment_months: string[];
  unpaid_paise: number; late_payment_months: { wage_month: string; days_late: number }[]; since: string;
}
interface Defaulters { as_of: string; defaulters: Defaulter[]; note: string }
interface ComplianceCase {
  case_id: string; establishment_id: string; legal_name: string | null; kind: CaseKind; wage_months: string[];
  amount_paise: number; state: string; opened_at: string;
  history: { at: string; by_role: string; action: string; note: string }[];
}
interface CaseDetails extends ComplianceCase {
  open_demands: { demand_id: string; kind: string; amount_paise: number; wage_month: string }[];
}
interface VishwasApplication {
  application_id: string; establishment_id: string; legal_name: string | null; demand_ids: string[];
  damages_paise: number; revised_paise: number | null; proposed_revised_paise: number; state: "SUBMITTED" | "APPROVED" | "REJECTED";
  decision_note: string | null;
}

function latestMonths(months: string[]): string[] {
  return [...months].sort((a, b) => b.localeCompare(a)).slice(0, 12);
}

function caseMonths(item: Defaulter, kind: CaseKind): string[] {
  if (kind === "NON_PAYMENT") return latestMonths(item.non_payment_months);
  if (kind === "NON_FILING") return latestMonths(item.non_filing_months);
  if (kind === "LATE_PAYMENT_DAMAGES") return latestMonths(item.late_payment_months.map((month) => month.wage_month));
  return [];
}

function MonthList({ months }: { months: string[] }) {
  return <><p>{months.length} month{months.length === 1 ? "" : "s"} in total</p>
    {months.length ? <ul>{latestMonths(months).map((month) => <li key={month}>{month}</li>)}</ul> : null}</>;
}

function OpenCaseForm({ item, busy, onOpen }: {
  item: Defaulter; busy: boolean; onOpen: (item: Defaulter, kind: CaseKind, note: string) => void;
}) {
  const [kind, setKind] = useState<CaseKind>(item.non_payment_months.length ? "NON_PAYMENT" : "NON_FILING");
  const [note, setNote] = useState("");
  const months = caseMonths(item, kind);
  return <form className="stack" aria-label={`Open case for ${item.establishment_id}`}
    onSubmit={(e) => { e.preventDefault(); onOpen(item, kind, note.trim()); }}>
    <label>Kind <select value={kind} disabled={busy} onChange={(e) => setKind(e.target.value as CaseKind)}>
      {(Object.keys(kindLabels) as CaseKind[]).map((value) => <option key={value} value={value}>{kindLabels[value]}</option>)}
    </select></label>
    <p>Months included: {months.length ? months.join(", ") : "No specific wage months"}.</p>
    <p>Case amount: {rupees(kind === "NON_PAYMENT" ? item.unpaid_paise : 0)}</p>
    <label>Note <textarea required minLength={10} maxLength={1000} value={note} disabled={busy}
      onChange={(e) => setNote(e.target.value)} /></label>
    <button type="submit" className="primary" disabled={busy}>Open case</button>
  </form>;
}

export function CompliancePage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  const compliance = role === "fo.da_compliance";
  const apfc = role === "fo.apfc";
  const canReadDefaulters = compliance || apfc || role === "fo.oic";
  const canReadCases = canReadDefaulters || role === "do.staff";
  const defaulters = useQuery({ queryKey: ["office-compliance-defaulters"], enabled: canReadDefaulters, retry: false,
    queryFn: () => api<Envelope<Defaulters>>(`${base}/defaulters`) });
  const cases = useQuery({ queryKey: ["office-compliance-cases", "OPEN"], enabled: canReadCases, retry: false,
    queryFn: () => api<Envelope<ComplianceCase[]>>(`${base}/cases?status=OPEN`) });
  const details = useQuery({ queryKey: ["office-compliance-case", selectedCase], enabled: canReadCases && !!selectedCase, retry: false,
    queryFn: () => api<Envelope<CaseDetails>>(`${base}/cases/${encodeURIComponent(selectedCase!)}`) });
  const vishwas = useQuery({ queryKey: ["office-compliance-vishwas"], enabled: apfc, retry: false,
    queryFn: () => api<Envelope<VishwasApplication[]>>(`${base}/vishwas-applications`) });

  async function run(work: () => Promise<string | null>) {
    setBusy(true); setError(null); setNotice(null);
    try { const message = await work(); if (message) setNotice(message); }
    catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  async function reload() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["office-compliance-defaulters"] }),
      qc.invalidateQueries({ queryKey: ["office-compliance-cases"] }),
      qc.invalidateQueries({ queryKey: ["office-compliance-case"] }),
      qc.invalidateQueries({ queryKey: ["office-compliance-vishwas"] }),
    ]);
  }

  function openCase(item: Defaulter, kind: CaseKind, note: string) {
    void run(async () => {
      if (note.length < 10) throw new Error("Enter a note of at least 10 characters.");
      const result = await command<Envelope<ComplianceCase>>("POST", `${base}/cases`, {
        establishment_id: item.establishment_id, kind, wage_months: caseMonths(item, kind),
        amount_paise: kind === "NON_PAYMENT" ? item.unpaid_paise : 0, note,
      });
      setSelectedCase(result.data.case_id);
      await reload();
      return `Case ${result.data.case_id} opened for ${item.establishment_id}.`;
    });
  }

  function decide(e: FormEvent<HTMLFormElement>, item: VishwasApplication) {
    e.preventDefault();
    const form = e.currentTarget;
    const submitter = (e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value;
    if (decision !== "APPROVE" && decision !== "REJECT") return;
    void run(async () => {
      const note = String(new FormData(form).get("note") ?? "").trim();
      if (note.length < 5) throw new Error("Enter a decision note of at least 5 characters.");
      const amount = decision === "APPROVE" ? item.proposed_revised_paise : item.damages_paise;   // the backend binds the code to these
      const token = await stepUp.ask({ action: "decide-vishwas", resourceId: item.application_id, amountPaise: amount,
        summary: `${decision === "APPROVE" ? "Approve" : "Reject"} illustrative VISHWAS application ${item.application_id} for ${rupees(amount)}` });
      if (!token) return null;
      await command("POST", `${base}/vishwas-applications/${encodeURIComponent(item.application_id)}/decisions`,
        { decision, note }, { stepUpToken: token });
      form.reset();
      await reload();
      return `Application ${item.application_id} ${decision === "APPROVE" ? "approved" : "rejected"}.`;
    });
  }

  return <main className="stack">
    <PageHeader eyebrow="Regional office" title="Compliance" current="Compliance"
      description="Review defaults, open compliance cases, and decide illustrative VISHWAS settlements." />
    <ProblemMessage error={error ?? session.error ?? defaulters.error ?? cases.error ?? details.error ?? vishwas.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {session.isLoading ? <p role="status">Loading office role…</p> : null}

    {canReadDefaulters ? <section className="card stack" aria-labelledby="defaulters-heading"><h2 id="defaulters-heading">Defaulting establishments</h2>
      {defaulters.isLoading ? <p role="status">Loading defaulters…</p> : null}
      {defaulters.data ? <><p>As of {defaulters.data.data.as_of}</p><p className="muted">{defaulters.data.data.note}</p>
        <p className="muted">Showing up to the 12 latest months for each kind of default; counts cover all months.</p></> : null}
      {defaulters.data?.data.defaulters.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Establishment</th><th scope="col">Since</th><th scope="col">Returns not filed</th>
        <th scope="col">Dues not paid</th><th scope="col">Unpaid amount</th><th scope="col">Late payments</th>
        {compliance ? <th scope="col">Action</th> : null}
      </tr></thead><tbody>{defaulters.data.data.defaulters.map((item) => <tr key={item.establishment_id}>
        <th scope="row">{item.establishment_id}</th><td>{item.since}</td>
        <td><MonthList months={item.non_filing_months} /></td><td><MonthList months={item.non_payment_months} /></td>
        <td>{rupees(item.unpaid_paise)}</td><td><p>{item.late_payment_months.length} late payment months in total</p>
          {item.late_payment_months.length ? <ul>{[...item.late_payment_months]
            .sort((a, b) => b.wage_month.localeCompare(a.wage_month)).slice(0, 12).map((month) =>
              <li key={month.wage_month}>{month.wage_month} · {month.days_late} days late</li>)}</ul> : null}</td>
        {compliance ? <td><OpenCaseForm item={item} busy={busy} onOpen={openCase} /></td> : null}
      </tr>)}</tbody></table></div> : defaulters.data ? <p className="muted">No defaulting establishments recorded.</p> : null}
    </section> : null}

    {canReadCases ? <section className="card stack" aria-labelledby="cases-heading"><h2 id="cases-heading">Open compliance cases</h2>
      {cases.isLoading ? <p role="status">Loading cases…</p> : null}
      {cases.data?.data.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Case</th><th scope="col">Establishment</th><th scope="col">Kind</th><th scope="col">Wage months</th>
        <th scope="col">Amount</th><th scope="col">State</th><th scope="col">Opened</th><th scope="col">Action</th>
      </tr></thead><tbody>{cases.data.data.map((item) => <tr key={item.case_id}>
        <th scope="row">{item.case_id}</th><td>{item.legal_name ?? item.establishment_id} · {item.establishment_id}</td>
        <td>{kindLabels[item.kind]}</td><td>{item.wage_months.join(", ") || "—"}</td><td>{rupees(item.amount_paise)}</td>
        <td>{item.state}</td><td>{item.opened_at}</td><td><button type="button" aria-label={`Details for case ${item.case_id}`}
          aria-expanded={selectedCase === item.case_id} aria-controls={selectedCase ? "compliance-case-details" : undefined}
          onClick={() => setSelectedCase(item.case_id)}>Details</button></td>
      </tr>)}</tbody></table></div> : cases.data ? <p className="muted">No open compliance cases.</p> : null}
      {selectedCase ? <div id="compliance-case-details" className="stack" aria-live="polite">
        <h3>Case details · {selectedCase}</h3>
        {details.isLoading ? <p role="status">Loading case details…</p> : null}
        {details.data ? <><dl>
          <div><dt>Establishment</dt><dd>{details.data.data.legal_name ?? details.data.data.establishment_id} · {details.data.data.establishment_id}</dd></div>
          <div><dt>Kind</dt><dd>{kindLabels[details.data.data.kind]}</dd></div>
          <div><dt>Wage months</dt><dd>{details.data.data.wage_months.join(", ") || "—"}</dd></div>
          <div><dt>Amount</dt><dd>{rupees(details.data.data.amount_paise)}</dd></div>
          <div><dt>State</dt><dd>{details.data.data.state}</dd></div>
          <div><dt>Opened</dt><dd>{details.data.data.opened_at}</dd></div>
        </dl><h4>History</h4>
          {details.data.data.history.length ? <ol>{details.data.data.history.map((entry, index) => <li key={`${entry.at}-${index}`}>
            {entry.at} · {entry.by_role} · {entry.action.replaceAll("_", " ")} · {entry.note}
          </li>)}</ol> : <p className="muted">No history recorded.</p>}
          <h4>Open demands</h4>
          {details.data.data.open_demands.length ? <div className="table-scroll"><table><thead><tr>
            <th scope="col">Demand</th><th scope="col">Kind</th><th scope="col">Wage month</th><th scope="col">Amount</th>
          </tr></thead><tbody>{details.data.data.open_demands.map((item) => <tr key={item.demand_id}>
            <th scope="row">{item.demand_id}</th><td>{item.kind.replaceAll("_", " ")}</td><td>{item.wage_month}</td>
            <td>{rupees(item.amount_paise)}</td></tr>)}</tbody></table></div> : <p className="muted">No open demands.</p>}
        </> : null}
        <div className="actions"><button type="button" onClick={() => setSelectedCase(null)}>Close details</button></div>
      </div> : null}
    </section> : null}

    {apfc ? <section className="card stack" aria-labelledby="vishwas-office-heading"><h2 id="vishwas-office-heading">VISHWAS applications</h2>
      <p className="muted">Illustrative settlement of 14B damages; 7Q interest is not covered. Approval sets 30% of damages, rounded down to whole rupees.</p>
      {vishwas.isLoading ? <p role="status">Loading VISHWAS applications…</p> : null}
      {vishwas.data?.data.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Application</th><th scope="col">Establishment</th><th scope="col">Demands</th><th scope="col">Damages</th>
        <th scope="col">Revised amount</th><th scope="col">State</th><th scope="col">Decision note</th><th scope="col">Decision</th>
      </tr></thead><tbody>{vishwas.data.data.map((item) => <tr key={item.application_id}>
        <th scope="row">{item.application_id}</th><td>{item.legal_name ?? item.establishment_id} · {item.establishment_id}</td>
        <td>{item.demand_ids.join(", ")}</td><td>{rupees(item.damages_paise)}</td><td>{rupees(item.revised_paise)}</td>
        <td>{item.state}</td><td>{item.decision_note ?? "—"}</td><td>{item.state === "SUBMITTED" ?
          <form className="stack" aria-label={`Decide VISHWAS application ${item.application_id}`} onSubmit={(e) => decide(e, item)}>
            <label>Decision note <input name="note" required minLength={5} maxLength={500} disabled={busy} /></label>
            <div className="actions"><button type="submit" value="APPROVE" className="primary" disabled={busy}>Approve</button>
              <button type="submit" value="REJECT" disabled={busy}>Reject</button></div>
          </form> : "—"}</td>
      </tr>)}</tbody></table></div> : vishwas.data ? <p className="muted">No VISHWAS applications recorded.</p> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </main>;
}
