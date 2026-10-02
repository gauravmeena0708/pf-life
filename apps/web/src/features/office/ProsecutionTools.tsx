import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";

/** P2.11c on the office's inquiry screen: a 26B membership dispute (registration by the SS, the order by the RPFC-II or above)
 *  and prosecution (the circle officer's show-cause notice, the RPFC's sanction, the Enforcement Officer's complaint). */
const base = "/api/v1/office/compliance";
const field = (f: FormData, name: string) => String(f.get(name) ?? "").trim();
type Run = (work: () => Promise<unknown>, ok: string, form?: HTMLFormElement) => void;
type Ask = (request: { action: string; resourceId: string; amountPaise?: number; summary: string }) => Promise<string | null>;
interface Action { kind: string; at: string; detail: Record<string, unknown> }
interface Disputed { name: string; uan?: string | null; claimed_from: string }

export function MembershipDisputeForm({ busy, run, ask }: { busy: boolean; run: Run; ask: Ask }) {
  const [rows, setRows] = useState(1);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const employees = Array.from({ length: rows }, (_, i) => ({ name: field(f, `name-${i}`), claimed_from: field(f, `from-${i}`),
      ...(field(f, `uan-${i}`) ? { uan: field(f, `uan-${i}`) } : {}) }));
    const establishmentId = field(f, "establishment_id");
    const token = await ask({ action: "register-26b", resourceId: establishmentId, summary: `Register a 26B dispute for ${establishmentId}` }); if (!token) return;
    run(() => command("POST", `${base}/membership-disputes`, { establishment_id: establishmentId, trigger: field(f, "trigger"), employees,
      contributory_uans: Number(f.get("contributory_uans")), note: field(f, "note") }, { stepUpToken: token }), "Dispute registered and allotted.", form);
  }
  return <form className="card stack" aria-labelledby="dispute-heading" onSubmit={(e) => void submit(e)}>
    <h2 id="dispute-heading">Membership dispute (Para 26B)</h2>
    <p className="muted small">Whether an employee is a member, and from when. Heard by an RPFC-II or above, as an inquiry (Compliance Manual ch. 4).</p>
    <div className="form-row"><label>Establishment ID<input name="establishment_id" required defaultValue="EST-DEMO-0001" /></label>
      <label>Raised by<select name="trigger"><option value="EMPLOYEE_COMPLAINT">An employee's complaint</option><option value="INSPECTOR_OBSERVATION">An inspector's observation</option>
        <option value="DURING_7A">A 7A inquiry</option><option value="UNION_COMPLAINT">A union's complaint</option></select></label>
      <label>Contributory UANs<input name="contributory_uans" type="number" min="0" required /></label></div>
    <fieldset className="stack"><legend>Employees in dispute</legend>
      {Array.from({ length: rows }, (_, i) => <div className="form-row" key={i}>
        <label>Name<input name={`name-${i}`} required /></label><label>UAN (if any)<input name={`uan-${i}`} /></label>
        <label>Member from (claimed)<input name={`from-${i}`} type="date" required /></label></div>)}
      <div className="actions"><button type="button" onClick={() => setRows((n) => n + 1)}>Add an employee</button></div></fieldset>
    <label>Note<textarea name="note" required minLength={10} /></label>
    <div className="actions"><button className="primary" disabled={busy} type="submit">Register dispute</button></div>
  </form>;
}

export function MembershipOrderForm({ caseId, actions, busy, run, ask }: { caseId: string; actions: Action[]; busy: boolean; run: Run; ask: Ask }) {
  const disputed = (actions.find((a) => a.kind === "DISPUTE")?.detail.employees ?? []) as Disputed[];
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const decisions = disputed.map((d, i) => {
      const eligible = f.get(`eligible-${i}`) === "yes";
      return { name: d.name, ...(d.uan ? { uan: d.uan } : {}), eligible, ...(eligible ? { from_date: field(f, `from-${i}`) } : {}) };
    });
    const token = await ask({ action: "pass-order", resourceId: caseId, amountPaise: 0, summary: `Pass the 26B order in ${caseId}` }); if (!token) return;
    run(() => command("POST", `${base}/cases/${caseId}/orders`, { kind: "26B", decisions, reasoning: field(f, "reasoning"), ex_parte: f.has("ex_parte") },
      { stepUpToken: token }), "26B order passed.", form);
  }
  return <form className="stack" aria-label="Pass 26B order" onSubmit={(e) => void submit(e)}>
    <h3>Order under Para 26B</h3>
    {disputed.map((d, i) => <fieldset key={d.name} className="form-row"><legend>{d.name}{d.uan ? ` (UAN ${d.uan})` : ""} — claims membership from {d.claimed_from}</legend>
      <label>Decision<select name={`eligible-${i}`} defaultValue="yes"><option value="yes">A member</option><option value="no">Not eligible</option></select></label>
      <label>Member from<input name={`from-${i}`} type="date" defaultValue={d.claimed_from} /></label></fieldset>)}
    <label>Findings and reasons<textarea name="reasoning" required /></label>
    <label><input type="checkbox" name="ex_parte" /> Ex parte (only after due service, the employer absent)</label>
    <div className="actions"><button className="primary" disabled={busy} type="submit">Pass 26B order</button></div>
  </form>;
}

interface Step { step: string; by: string; at: string; note: string; late?: boolean; court?: string; complaint_no?: string }
interface Prosecution { prosecution_id: string; establishment_id: string; inquiry_case_id: string | null; offence: string; particulars: string;
  state: string; reply_due: string; reply_overdue: boolean; history: Step[]; legal_case_id: string | null }
const OFFENCE: Record<string, string> = { NON_PAYMENT: "Dues not paid after a 7A order", NON_FILING_RETURNS: "Returns not filed", OTHER: "Other" };
const STATE: Record<string, string> = { SCN_ISSUED: "Show-cause issued", REPLIED: "Employer replied", SANCTIONED: "Sanctioned",
  COMPLAINT_FILED: "Complaint in court", DROPPED: "Dropped", CONVICTED: "Convicted", ACQUITTED: "Acquitted" };

export function ProsecutionPanel({ role, busy, run, ask }: { role: string; busy: boolean; run: Run; ask: Ask }) {
  const list = useQuery({ queryKey: ["prosecutions"], retry: false, queryFn: () => api<Envelope<Prosecution[]>>(`${base}/prosecutions`) });
  async function issue(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); const caseId = field(f, "case_id");
    const token = await ask({ action: "issue-prosecution-scn", resourceId: caseId, summary: `Issue a prosecution show-cause notice on ${caseId}` }); if (!token) return;
    run(() => command("POST", `${base}/cases/${encodeURIComponent(caseId)}/prosecutions`, { offence: field(f, "offence"), particulars: field(f, "particulars") },
      { stepUpToken: token }), "Show-cause notice issued (7 working days to reply).", form);
  }
  function step(e: FormEvent<HTMLFormElement>, id: string, name: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    run(() => command("POST", `${base}/prosecutions/${id}/steps`, { step: name, note: field(f, "note"),
      ...(name === "COMPLAINT" ? { court: field(f, "court"), complaint_no: field(f, "complaint_no") } : {}) }), "Recorded.", form);
  }
  const mine = (p: Prosecution) => (role === "fo.oic" && (p.state === "REPLIED" || (p.state === "SCN_ISSUED" && p.reply_overdue)) ? "SANCTION"
    : role === "fo.eo" && p.state === "SANCTIONED" ? "COMPLAINT" : role === "fo.apfc" && ["SCN_ISSUED", "REPLIED", "SANCTIONED"].includes(p.state) ? "DROP" : null);
  return <section className="card stack" aria-labelledby="prosecution-heading">
    <h2 id="prosecution-heading">Prosecutions</h2>
    <p className="muted small">Show-cause first (at least 7 working days); for unpaid dues only after a 7A order left unpaid; the RPFC sanctions; an
      Inspector (the Enforcement Officer) files the complaint within 7 days (Compliance Manual 5.2).</p>
    {role === "fo.apfc" ? <form className="stack" aria-label="Issue prosecution show-cause notice" onSubmit={(e) => void issue(e)}>
      <div className="form-row"><label>Case ID<input name="case_id" required /></label>
        <label>Offence<select name="offence">{Object.entries(OFFENCE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
      <label>Particulars<textarea name="particulars" required minLength={10} /></label>
      <div className="actions"><button className="primary" disabled={busy} type="submit">Issue show-cause notice</button></div></form> : null}
    {list.data && !list.data.data?.length ? <p className="muted">No prosecutions.</p> : null}
    {list.data?.data?.map((p) => { const next = mine(p); return <article key={p.prosecution_id} className="profile-card stack" aria-label={`Prosecution ${p.prosecution_id}`}>
      <h3>{p.prosecution_id} · {p.establishment_id} <span className="state-pill">{STATE[p.state] ?? p.state}</span>
        {p.reply_overdue ? <strong className="inquiry-overdue">Reply overdue</strong> : null}</h3>
      <p>{OFFENCE[p.offence] ?? p.offence}: {p.particulars}</p>
      <ol className="inquiry-steps">{p.history.map((h, i) => <li key={i}>{h.step} · {new Date(h.at).toLocaleDateString("en-IN")} — {h.note}
        {h.court ? ` (${h.court}, ${h.complaint_no})` : ""}{h.late ? " · late" : ""}</li>)}</ol>
      {next ? <form className="stack" aria-label={`${next} ${p.prosecution_id}`} onSubmit={(e) => step(e, p.prosecution_id, next)}>
        {next === "COMPLAINT" ? <div className="form-row"><label>Court<input name="court" required /></label><label>Complaint number<input name="complaint_no" required /></label></div> : null}
        <label>Note<textarea name="note" required /></label>
        <div className="actions"><button className="primary" disabled={busy} type="submit">{next === "SANCTION" ? "Sanction prosecution" : next === "COMPLAINT" ? "Record complaint filed" : "Drop (default set right)"}</button></div>
      </form> : null}
    </article>; })}
  </section>;
}
