import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import "./InquiriesPage.css";

/** Inspections and 7A inquiries (Compliance Manual ch. 2): EO report → DA (T+3) → SS (T+5) → circle officer (T+7) → registration with a
 *  diary number → the officer allotted by size → summons → hearings → the 7A order. */
const base = "/api/v1/office/compliance";
interface Step { stage: string; note: string | null; occurred_at: string; overdue: boolean }
export interface Inspection {
  inspection_id: string; establishment_id: string; purpose: string; period_from: string; period_to: string; state: string;
  due_at: string; overdue: boolean; report: { employees_found: number; employees_not_enrolled: number; findings: string; dues_estimate_paise: number; recommendation: string } | null;
  steps: Step[];
}
interface Action { kind: string; at: string; detail: Record<string, unknown> }
export interface InquiryCase {
  case_id: string; establishment_id: string; legal_name: string | null; kind: string; state: string;
  inquiry?: { diary_no: string; officer_rank: string; officer_subject: string; state: string; period_from: string; period_to: string;
    contributory_uans: number; order_due_at: string | null; actions: Action[] };
}
const STATE_TEXT: Record<string, string> = {
  SCHEDULED: "Scheduled — EO to inspect", REPORTED: "Reported — DA to note", DA_NOTED: "DA noted — SS to note", SS_NOTED: "SS noted — circle officer to decide",
  DECIDED_INITIATE: "Inquiry to be registered", CLOSED: "Closed — no action", REGISTERED: "Registered", SUMMONED: "Summons issued",
  HEARING: "Hearing in progress", CONCLUDED: "Concluded — order due", ORDERED: "Order passed",
};
const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");
const field = (f: FormData, name: string) => String(f.get(name) ?? "").trim();

export function InquiriesPage() {
  const qc = useQueryClient(); const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const inspections = useQuery({ queryKey: ["inspections"], enabled: !!role, retry: false,
    queryFn: () => api<Envelope<Inspection[]>>(`${base}/inspections`) });
  const inquiries = useQuery({ queryKey: ["inquiries"], enabled: ["fo.apfc", "fo.oic", "fo.ss", "fo.da_compliance"].includes(role), retry: false,
    queryFn: () => api<Envelope<InquiryCase[]>>(`${base}/cases?type=INQUIRY_7A`) });
  const detail = useQuery({ queryKey: ["inquiry", open], enabled: !!open, retry: false,
    queryFn: () => api<Envelope<InquiryCase>>(`${base}/cases/${encodeURIComponent(open ?? "")}`) });

  async function run(work: () => Promise<unknown>, ok: string, form?: HTMLFormElement) {
    setBusy(true); setError(null); setNotice("");
    try { await work(); form?.reset(); setNotice(ok); await qc.invalidateQueries(); } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  function schedule(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(() => command("POST", `${base}/inspections`, { establishment_id: field(f, "establishment_id"), purpose: field(f, "purpose"),
      period_from: field(f, "period_from"), period_to: field(f, "period_to"), note: field(f, "note") }), "Inspection scheduled.", form);
  }
  function report(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(() => command("POST", `${base}/inspections/${id}/reports`, { visited_on: field(f, "visited_on"),
      employees_found: Number(f.get("employees_found")), employees_not_enrolled: Number(f.get("employees_not_enrolled")),
      wages_paise_monthly: Math.round(Number(f.get("wages")) * 100), findings: field(f, "findings"),
      dues_estimate_paise: Math.round(Number(f.get("dues")) * 100), recommendation: field(f, "recommendation") }), "Report submitted.", form);
  }
  function note(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const decision = role === "fo.apfc" ? field(f, "decision") : undefined;
    void run(() => command("POST", `${base}/inspections/${id}/processing-notes`, { note: field(f, "note"), ...(decision ? { decision } : {}) }),
      decision ? "Decision recorded." : "Note recorded.", form);
  }
  function register(e: FormEvent<HTMLFormElement>, item: Inspection) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(() => command("POST", `${base}/cases`, { establishment_id: item.establishment_id, kind: "INQUIRY_7A", dispute: field(f, "dispute"),
      period_from: item.period_from, period_to: item.period_to, inspection_id: item.inspection_id,
      contributory_uans: Number(f.get("contributory_uans")), note: field(f, "note") }), "Inquiry registered and allotted.", form);
  }
  async function summons(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const token = await stepUp.ask({ action: "issue-summons", resourceId: id, summary: `Issue summons for ${id}` }); if (!token) return;
    void run(() => command("POST", `${base}/cases/${id}/notices`, { hearing_at: new Date(field(f, "hearing_at")).toISOString(),
      scope: field(f, "scope"), period: field(f, "period") }, { stepUpToken: token }), "Summons issued and served.", form);
  }
  function hearing(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); const concluded = f.has("concluded");
    void run(() => command("POST", `${base}/cases/${id}/hearings`, { held_at: new Date(field(f, "held_at")).toISOString(),
      employer_present: f.has("employer_present"), eo_present: f.has("eo_present"), proceedings: field(f, "proceedings"),
      ...(concluded ? { concluded: true } : { next_hearing_at: new Date(field(f, "next_hearing_at")).toISOString() }),
      ...(field(f, "adjournment_reason") ? { adjournment_reason: field(f, "adjournment_reason") } : {}) }), "Daily order recorded.", form);
  }
  async function order(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const paise = (name: string) => Math.round(Number(f.get(name) || 0) * 100);
    const dues = [{ wage_month: field(f, "wage_month"), ac1_employee_paise: paise("ac1_employee"), ac1_employer_paise: paise("ac1_employer"),
      ac10_pension_paise: paise("ac10"), ac21_edli_paise: paise("ac21"), ac2_admin_paise: paise("ac2") }];
    const total = Object.entries(dues[0]).filter(([k]) => k.endsWith("_paise")).reduce((sum, [, v]) => sum + Number(v), 0);
    const token = await stepUp.ask({ action: "pass-order", resourceId: id, amountPaise: total, summary: `Pass the 7A order for ${rupees(total)}` });
    if (!token) return;
    void run(() => command("POST", `${base}/cases/${id}/orders`, { kind: "7A", dues, reasoning: field(f, "reasoning"), ex_parte: f.has("ex_parte") },
      { stepUpToken: token }), "Order passed; the demand is raised.", form);
  }

  const inq = detail.data?.data.inquiry;
  const summonsActions = inq?.actions.filter((a) => a.kind === "SUMMONS") ?? [];
  return <section className="stack" aria-labelledby="inquiries-heading">
    <PageHeader id="inquiries-heading" eyebrow="Compliance" title="Inspections and 7A inquiries" current="Inspections and inquiries"
      description="From the Enforcement Officer's report to the order under section 7A, with each stage's time limit (Compliance Manual, chapter 2)." />
    <ProblemMessage error={error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {role === "fo.apfc" ? <form className="card stack" aria-labelledby="schedule-heading" onSubmit={schedule}>
      <h2 id="schedule-heading">Schedule an inspection</h2>
      <div className="form-row"><label>Establishment ID<input name="establishment_id" required defaultValue="EST-DEMO-0001" /></label>
        <label>Purpose<select name="purpose" defaultValue="COMPLAINT"><option value="COMPLAINT">Complaint</option><option value="CAIU_ALLOCATION">CAIU allocation</option>
          <option value="DEFAULTER">Defaulter</option><option value="SURVEY">Survey</option></select></label>
        <label>Period from<input name="period_from" type="month" required /></label><label>Period to<input name="period_to" type="month" required /></label></div>
      <label>Note<textarea name="note" required /></label>
      <p className="muted small">An Enforcement Officer of the office is assigned.</p>
      <div className="actions"><button className="primary" disabled={busy} type="submit">Schedule</button></div></form> : null}

    <section className="card stack" aria-labelledby="inspections-heading"><h2 id="inspections-heading">Inspections</h2>
      <ProblemMessage error={inspections.error} />
      {inspections.data && !inspections.data.data?.length ? <p className="muted">No inspections.</p> : null}
      {inspections.data?.data?.map((item) => <article key={item.inspection_id} className="profile-card stack" aria-label={`Inspection ${item.inspection_id}`}>
        <h3>{item.inspection_id} · {item.establishment_id} <span className="state-pill">{STATE_TEXT[item.state] ?? item.state}</span>
          {item.overdue ? <strong className="inquiry-overdue">Overdue</strong> : null}</h3>
        <p className="muted small">{item.purpose} · {item.period_from} to {item.period_to} · next step due {when(item.due_at)}</p>
        {item.report ? <p>{item.report.findings} · found {item.report.employees_found}, not enrolled {item.report.employees_not_enrolled} · estimated dues {rupees(item.report.dues_estimate_paise)}</p> : null}
        {item.steps.length ? <ol className="inquiry-steps">{item.steps.map((s) => <li key={s.stage + s.occurred_at}>{s.stage} · {when(s.occurred_at)}{s.overdue ? " · late" : ""}{s.note ? ` — ${s.note}` : ""}</li>)}</ol> : null}
        {role === "fo.eo" && item.state === "SCHEDULED" ? <form className="stack" aria-label={`Report ${item.inspection_id}`} onSubmit={(e) => report(e, item.inspection_id)}>
          <div className="form-row"><label>Visited on<input name="visited_on" type="date" required /></label><label>Employees found<input name="employees_found" type="number" min="0" required /></label>
            <label>Not enrolled<input name="employees_not_enrolled" type="number" min="0" required /></label><label>Monthly wages (₹)<input name="wages" type="number" min="0" step="0.01" required /></label>
            <label>Dues estimated (₹)<input name="dues" type="number" min="0" step="0.01" required /></label></div>
          <label>Findings<textarea name="findings" required /></label>
          <label>Recommendation<select name="recommendation"><option value="INITIATE_7A_DUES">Inquiry under 7A — dues</option>
            <option value="INITIATE_7A_APPLICABILITY">Inquiry under 7A — applicability</option><option value="NO_ACTION">No action</option></select></label>
          <div className="actions"><button className="primary" disabled={busy} type="submit">Submit report</button></div></form> : null}
        {(role === "fo.da_compliance" && item.state === "REPORTED") || (role === "fo.ss" && item.state === "DA_NOTED") || (role === "fo.apfc" && item.state === "SS_NOTED")
          ? <form className="stack" aria-label={`Process ${item.inspection_id}`} onSubmit={(e) => note(e, item.inspection_id)}>
            {role === "fo.apfc" ? <label>Decision<select name="decision"><option value="INITIATE_7A">Initiate an inquiry under 7A</option><option value="NO_ACTION">No action</option></select></label> : null}
            <label>Note<textarea name="note" required /></label>
            <div className="actions"><button className="primary" disabled={busy} type="submit">{role === "fo.apfc" ? "Record decision" : "Put up the note"}</button></div></form> : null}
        {["fo.ss", "fo.da_compliance"].includes(role) && item.state === "DECIDED_INITIATE"
          ? <form className="stack" aria-label={`Register inquiry ${item.inspection_id}`} onSubmit={(e) => register(e, item)}>
            <div className="form-row"><label>Dispute<select name="dispute"><option value="DUES">Determination of dues</option><option value="APPLICABILITY">Applicability</option></select></label>
              <label>Contributory UANs<input name="contributory_uans" type="number" min={item.report?.employees_found ?? 0} defaultValue={item.report?.employees_found ?? 0} required /></label></div>
            <label>Note<textarea name="note" required /></label>
            <div className="actions"><button className="primary" disabled={busy} type="submit">Register on e-Proceedings</button></div></form> : null}
      </article>)}
    </section>

    {inquiries.data ? <section className="card stack" aria-labelledby="inquiry-list-heading"><h2 id="inquiry-list-heading">Inquiries</h2>
      {!inquiries.data.data?.length ? <p className="muted">No inquiries.</p> : <div className="table-scroll"><table><thead><tr>
        <th scope="col">Case</th><th scope="col">Establishment</th><th scope="col">State</th><th scope="col" /></tr></thead>
        <tbody>{inquiries.data.data.map((c) => <tr key={c.case_id}><th scope="row">{c.case_id}</th><td>{c.legal_name ?? c.establishment_id}</td><td>{c.state}</td>
          <td><button type="button" onClick={() => setOpen(c.case_id)}>Open</button></td></tr>)}</tbody></table></div>}
    </section> : null}

    {inq && open ? <section className="card stack" aria-labelledby="inquiry-heading">
      <h2 id="inquiry-heading">{inq.diary_no} <span className="state-pill">{STATE_TEXT[inq.state] ?? inq.state}</span></h2>
      <p className="muted small">{detail.data?.data.legal_name ?? detail.data?.data.establishment_id} · {inq.period_from} to {inq.period_to} · {inq.contributory_uans} contributory UANs · allotted to the {inq.officer_rank}
        {inq.order_due_at ? ` · order due ${when(inq.order_due_at)}` : ""}</p>
      <ol className="inquiry-steps">{inq.actions.map((a, i) => <li key={i}><strong>{a.kind}</strong> · {when(a.at)}
        {a.kind === "SUMMONS" ? ` — hearing ${when(String(a.detail.hearing_at))}, served by e-mail and speed post` : null}
        {a.kind === "HEARING" ? ` — ${String(a.detail.proceedings)}${a.detail.employer_present ? "" : " (employer absent)"}` : null}
        {a.kind === "SUBMISSION" ? ` — employer: ${String(a.detail.text)}` : null}
        {a.kind === "ORDER" ? <pre className="inquiry-order">{String(a.detail.text)}</pre> : null}</li>)}</ol>
      {["fo.apfc", "fo.oic"].includes(role) && ["REGISTERED", "SUMMONED", "HEARING"].includes(inq.state) && summonsActions.length === 0
        ? <form className="stack" aria-label="Issue summons" onSubmit={(e) => void summons(e, open)}>
          <div className="form-row"><label>Hearing (virtual)<input name="hearing_at" type="datetime-local" required /></label>
            <label>Scope<input name="scope" required /></label><label>Period<input name="period" required defaultValue={`${inq.period_from} to ${inq.period_to}`} /></label></div>
          <div className="actions"><button className="primary" disabled={busy} type="submit">Issue summons</button></div></form> : null}
      {["fo.apfc", "fo.oic"].includes(role) && ["SUMMONED", "HEARING"].includes(inq.state)
        ? <form className="stack" aria-label="Record hearing" onSubmit={(e) => hearing(e, open)}>
          <div className="form-row"><label>Held at<input name="held_at" type="datetime-local" required /></label>
            <label>Next hearing<input name="next_hearing_at" type="datetime-local" /></label><label>Adjournment reason (beyond 7 days)<input name="adjournment_reason" /></label></div>
          <label><input type="checkbox" name="employer_present" defaultChecked /> Employer present</label><label><input type="checkbox" name="eo_present" defaultChecked /> EO present</label>
          <label><input type="checkbox" name="concluded" /> Hearing concluded (reserved for orders)</label>
          <label>Daily order<textarea name="proceedings" required /></label>
          <div className="actions"><button className="primary" disabled={busy} type="submit">Record daily order</button></div></form> : null}
      {["fo.apfc", "fo.oic"].includes(role) && inq.state === "CONCLUDED"
        ? <form className="stack" aria-label="Pass 7A order" onSubmit={(e) => void order(e, open)}>
          <div className="form-row"><label>Wage month<input name="wage_month" type="month" required /></label>
            <label>A/c 1 employee (₹)<input name="ac1_employee" type="number" min="0" step="0.01" defaultValue="0" /></label>
            <label>A/c 1 employer (₹)<input name="ac1_employer" type="number" min="0" step="0.01" defaultValue="0" /></label>
            <label>A/c 10 pension (₹)<input name="ac10" type="number" min="0" step="0.01" defaultValue="0" /></label>
            <label>A/c 21 EDLI (₹)<input name="ac21" type="number" min="0" step="0.01" defaultValue="0" /></label>
            <label>A/c 2 admin (₹)<input name="ac2" type="number" min="0" step="0.01" defaultValue="0" /></label></div>
          <label>Findings and reasons<textarea name="reasoning" required /></label>
          <label><input type="checkbox" name="ex_parte" /> Ex parte (only after due service, the employer absent)</label>
          <div className="actions"><button className="primary" disabled={busy} type="submit">Pass order</button></div></form> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
