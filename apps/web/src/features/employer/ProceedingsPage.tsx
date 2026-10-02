import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import "../office/InquiriesPage.css";

/** The establishment's side of a 7A inquiry: the summons and hearing link, the daily orders, its replies, and the order. */
interface Action { kind: string; at: string; detail: Record<string, unknown> }
interface Proceeding {
  case_id: string; diary_no: string; dispute: string; period_from: string; period_to: string; officer_rank: string; state: string;
  summons: Action[]; daily_orders: Action[]; submissions: Action[]; order: Action | null;
}
const STATE: Record<string, string> = { REGISTERED: "Registered", SUMMONED: "Summons issued", HEARING: "Hearings in progress",
  CONCLUDED: "Reserved for orders", ORDERED: "Order passed" };
const when = (iso: unknown) => (iso ? new Date(String(iso)).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");

export function EmployerProceedingsPage() {
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const list = useQuery({ queryKey: ["employer-proceedings"], retry: false, queryFn: () => api<Envelope<Proceeding[]>>("/api/v1/employers/me/proceedings") });

  async function submit(e: FormEvent<HTMLFormElement>, caseId: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    setBusy(true); setError(null); setNotice("");
    try {
      await command("POST", `/api/v1/employers/me/proceedings/${encodeURIComponent(caseId)}/submissions`, {
        kind: String(f.get("kind")), text: String(f.get("text")).trim(),
        documents: String(f.get("documents") || "").split(",").map((d) => d.trim()).filter(Boolean) });
      form.reset(); setNotice("Your reply is on the record of the inquiry."); await qc.invalidateQueries({ queryKey: ["employer-proceedings"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <section className="stack" aria-labelledby="proceedings-heading">
    <PageHeader id="proceedings-heading" eyebrow="Compliance" title="Inquiries (e-Proceedings)" current="Inquiries"
      description="Inquiries under section 7A about your establishment: the summons, the virtual hearings, the daily orders and the order. Quote the diary number in every communication." />
    <ProblemMessage error={list.error} /><ProblemMessage error={error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {list.data?.data.length === 0 ? <p className="muted">There is no inquiry about your establishment.</p> : null}
    {list.data?.data.map((p) => <article key={p.case_id} className="card stack" aria-labelledby={`p-${p.case_id}`}>
      <h2 id={`p-${p.case_id}`}>{p.diary_no} <span className="state-pill">{STATE[p.state] ?? p.state}</span></h2>
      <p className="muted small">Section 7A · {p.dispute === "DUES" ? "determination of dues" : "applicability"} · {p.period_from} to {p.period_to} · before the {p.officer_rank}</p>
      {p.summons.map((s, i) => <p key={i}>Summons: hearing on <strong>{when(s.detail.hearing_at)}</strong> by video conference —{" "}
        <a href={String(s.detail.meeting_link)}>join the hearing</a>; case status on <a href={String(s.detail.case_status_url)}>e-Proceedings</a>. Scope: {String(s.detail.scope)}.</p>)}
      {p.daily_orders.length ? <><h3>Daily orders</h3><ol>{p.daily_orders.map((d, i) => <li key={i}>{when(d.detail.held_at)} — {String(d.detail.proceedings).replace(/\.?$/, ".")}
        {d.detail.next_hearing_at ? ` Next hearing: ${when(d.detail.next_hearing_at)}.` : ""}{d.detail.concluded && !/reserved for orders/i.test(String(d.detail.proceedings)) ? " Reserved for orders." : ""}</li>)}</ol></> : null}
      {p.submissions.length ? <><h3>Your replies</h3><ul>{p.submissions.map((s, i) => <li key={i}>{when(s.at)} — {String(s.detail.text)}</li>)}</ul></> : null}
      {p.order ? <><h3>Order</h3><p>Dues assessed: <strong>{rupees(Number(p.order.detail.total_paise))}</strong>{p.order.detail.ex_parte ? " (ex parte)" : ""}. Pay them by a direct challan against demand {String(p.order.detail.demand_id)}.</p>
        <pre className="inquiry-order">{String(p.order.detail.text)}</pre></>
        : <form className="stack" aria-label={`Reply in ${p.diary_no}`} onSubmit={(e) => void submit(e, p.case_id)}>
          <h3>Reply or file evidence</h3>
          <label>Kind<select name="kind"><option value="REPLY">Reply</option><option value="EVIDENCE">Evidence</option></select></label>
          <label>Text<textarea name="text" required /></label>
          <label>Documents (file names, comma-separated; signed PDFs)<input name="documents" /></label>
          <div className="actions"><button className="primary" disabled={busy} type="submit">Submit</button></div></form>}
    </article>)}
  </section>;
}
