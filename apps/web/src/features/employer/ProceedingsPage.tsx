import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { ScnReplies } from "./ScnReplies";
import { RecoveryCases } from "./RecoveryCases";
import "../office/InquiriesPage.css";

/** The establishment's side of a 7A inquiry: the summons and hearing link, the daily orders, its replies, and the order. */
interface Action { kind: string; at: string; detail: Record<string, unknown> }
interface Proceeding {
  case_id: string; diary_no: string; dispute: string; period_from: string; period_to: string; officer_rank: string; state: string;
  summons: Action[]; daily_orders: Action[]; submissions: Action[]; order: Action | null;
  applications?: Action[]; orders?: Action[];
}
const STATE: Record<string, string> = { REGISTERED: "Registered", SUMMONED: "Summons issued", HEARING: "Hearings in progress",
  CONCLUDED: "Reserved for orders", ORDERED: "Order passed" };
const GROUNDS: Record<string, string> = {
  NEW_EVIDENCE: "New and important evidence not available earlier despite due diligence",
  ERROR_APPARENT: "A mistake or error apparent on the face of the record",
  OTHER_SUFFICIENT: "Another sufficient reason",
  NOT_SERVED: "The notice was not duly served",
  SUFFICIENT_CAUSE: "A sufficient cause prevented appearance",
};
const APP_STATUS: Record<string, string> = {
  PENDING: "Pending", GRANTED: "Granted", REJECTED: "Rejected", SET_ASIDE: "Set aside",
};
const when = (iso: unknown) => {
  if (!iso) return "—";
  const d = new Date(String(iso));
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
};

function ApplicationForm({ p, busy, setBusy, setError, setNotice }: {
  p: Proceeding; busy: boolean; setBusy: (b: boolean) => void;
  setError: (e: unknown) => void; setNotice: (s: string) => void;
}) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<"REVIEW_7B" | "SET_ASIDE">("REVIEW_7B");
  const [grounds, setGrounds] = useState<string>("NEW_EVIDENCE");

  function onKindChange(next: "REVIEW_7B" | "SET_ASIDE") {
    setKind(next);
    setGrounds(next === "SET_ASIDE" ? "NOT_SERVED" : "NEW_EVIDENCE");
  }

  async function submitApp(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    setBusy(true); setError(null); setNotice("");
    try {
      await command("POST", `/api/v1/employers/me/proceedings/${encodeURIComponent(p.case_id)}/applications`, {
        kind, grounds, text: String(f.get("text")).trim(),
        documents: String(f.get("documents") || "").split(",").map((d) => d.trim()).filter(Boolean),
      });
      form.reset(); setNotice("Your application is on the record"); await qc.invalidateQueries({ queryKey: ["employer-proceedings"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <form className="stack" aria-label={`Apply for a review (section 7B) in ${p.diary_no}`} onSubmit={(e) => void submitApp(e)}>
    <h3>{kind === "SET_ASIDE" ? "Apply to set aside the ex-parte order (section 7A(4))" : "Apply for a review (section 7B)"}</h3>
    <label>Kind
      <select name="kind" value={kind} onChange={(e) => onKindChange(e.target.value as "REVIEW_7B" | "SET_ASIDE")}>
        <option value="REVIEW_7B">Apply for a review (section 7B)</option>
        {p.order?.detail.ex_parte ? <option value="SET_ASIDE">Apply to set aside the ex-parte order (section 7A(4))</option> : null}
      </select>
    </label>
    <p className="muted small">
      {kind === "SET_ASIDE" ? "Within 3 months of the order." : "Within 45 days of the order. A review is not an appeal: it lies only on these grounds."}
    </p>
    <label>Grounds
      <select name="grounds" value={grounds} onChange={(e) => setGrounds(e.target.value)}>
        {kind === "SET_ASIDE" ? <>
          <option value="NOT_SERVED">{GROUNDS.NOT_SERVED}</option>
          <option value="SUFFICIENT_CAUSE">{GROUNDS.SUFFICIENT_CAUSE}</option>
        </> : <>
          <option value="NEW_EVIDENCE">{GROUNDS.NEW_EVIDENCE}</option>
          <option value="ERROR_APPARENT">{GROUNDS.ERROR_APPARENT}</option>
          <option value="OTHER_SUFFICIENT">{GROUNDS.OTHER_SUFFICIENT}</option>
        </>}
      </select>
    </label>
    <label>Text<textarea name="text" required /></label>
    <label>Documents (file names, comma-separated; signed PDFs)<input name="documents" /></label>
    <div className="actions"><button className="primary" disabled={busy} type="submit">Submit</button></div>
  </form>;
}

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
    {list.data?.data.map((p) => {
      const hasPending = Boolean(p.applications?.some((a) => a.detail.status === "PENDING"));
      const superseded = (p.orders && p.orders.length > 1)
        ? (p.orders.find((o) => o.detail.superseded) ?? p.orders.find((o) => o !== p.order) ?? p.orders[0])
        : null;
      return <article key={p.case_id} className="card stack" aria-labelledby={`p-${p.case_id}`}>
        <h2 id={`p-${p.case_id}`}>{p.diary_no} <span className="state-pill">{STATE[p.state] ?? p.state}</span></h2>
        <p className="muted small">Section 7A · {p.dispute === "DUES" ? "determination of dues" : "applicability"} · {p.period_from} to {p.period_to} · before the {p.officer_rank}</p>
        {p.summons.map((s, i) => <p key={i}>Summons: hearing on <strong>{when(s.detail.hearing_at)}</strong> by video conference —{" "}
          <a href={String(s.detail.meeting_link)}>join the hearing</a>; case status on <a href={String(s.detail.case_status_url)}>e-Proceedings</a>. Scope: {String(s.detail.scope)}.</p>)}
        {p.daily_orders.length ? <><h3>Daily orders</h3><ol>{p.daily_orders.map((d, i) => <li key={i}>{when(d.detail.held_at)} — {String(d.detail.proceedings).replace(/\.?$/, ".")}
          {d.detail.next_hearing_at ? ` Next hearing: ${when(d.detail.next_hearing_at)}.` : ""}{d.detail.concluded && !/reserved for orders/i.test(String(d.detail.proceedings)) ? " Reserved for orders." : ""}</li>)}</ol></> : null}
        {p.submissions.length ? <><h3>Your replies</h3><ul>{p.submissions.map((s, i) => <li key={i}>{when(s.at)} — {String(s.detail.text)}</li>)}</ul></> : null}
        {p.order ? <><h3>Order</h3><p>Dues assessed: <strong>{rupees(Number(p.order.detail.total_paise))}</strong>{p.order.detail.ex_parte ? " (ex parte)" : ""}. Pay them by a direct challan against demand {String(p.order.detail.demand_id)}.</p>
          {superseded ? <p className="muted small">Earlier order replaced on review: <strong>{rupees(Number(superseded.detail.total_paise))}</strong></p> : null}
          <pre className="inquiry-order">{String(p.order.detail.text)}</pre></>
          : <form className="stack" aria-label={`Reply in ${p.diary_no}`} onSubmit={(e) => void submit(e, p.case_id)}>
            <h3>Reply or file evidence</h3>
            <label>Kind<select name="kind"><option value="REPLY">Reply</option><option value="EVIDENCE">Evidence</option></select></label>
            <label>Text<textarea name="text" required /></label>
            <label>Documents (file names, comma-separated; signed PDFs)<input name="documents" /></label>
            <div className="actions"><button className="primary" disabled={busy} type="submit">Submit</button></div></form>}
        {p.applications?.length ? <><h3>Applications</h3><ul>{p.applications.map((a, i) => {
          const k = (a.detail.kind || a.kind) === "SET_ASIDE" ? "Set aside under 7A(4)" : "Review under 7B";
          const g = GROUNDS[String(a.detail.grounds)] ?? String(a.detail.grounds);
          const st = APP_STATUS[String(a.detail.status)] ?? String(a.detail.status);
          return <li key={i}>{k} · {when(a.at)} — {g} <span className="state-pill">{st}</span></li>;
        })}</ul></> : null}
        {p.order && !hasPending ? <ApplicationForm p={p} busy={busy} setBusy={setBusy} setError={setError} setNotice={setNotice} /> : null}
      </article>;
    })}
    <ScnReplies />
    <RecoveryCases />
  </section>;
}
