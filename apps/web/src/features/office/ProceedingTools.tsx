import { useQuery } from "@tanstack/react-query";
import { type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";

/** P2.11b on the office's inquiry screen: the 14B / 7Q notice (DA, SS, circle officer), the 14B / 7Q orders, and after an order
 *  — review under 7B, setting aside an ex-parte order, reopening under 7C — and the administrative scrutiny of orders. */
const base = "/api/v1/office/compliance";
const field = (f: FormData, name: string) => String(f.get(name) ?? "").trim();
type Run = (work: () => Promise<unknown>, ok: string, form?: HTMLFormElement) => void;
type Ask = (request: { action: string; resourceId: string; amountPaise?: number; summary: string }) => Promise<string | null>;
interface Action { kind: string; at: string; detail: Record<string, unknown> }
interface NoticedDemand { demand_id: string; kind: string; wage_month: string; days_late: number; amount_paise: number }
const NEXT_HIGHER: Record<string, string> = { APFC: "RPFC-II", "RPFC-II": "RPFC-I", "RPFC-I": "ZONAL_ACC" };

export function DamagesNoticeForm({ busy, run }: { busy: boolean; run: Run }) {
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    run(() => command("POST", `${base}/cases`, { establishment_id: field(f, "establishment_id"), kind: "INQUIRY_14B",
      contributory_uans: Number(f.get("contributory_uans")), note: field(f, "note") }), "Notice drafted; it goes to the SS.", form);
  }
  return <form className="card stack" aria-labelledby="damages-heading" onSubmit={submit}>
    <h2 id="damages-heading">Damages notice (14B / 7Q)</h2>
    <p className="muted small">Periodic desk review: the notice covers every open auto-calculated 14B damages and 7Q interest demand of the
      establishment (Compliance Manual 3.2). SS endorses by T+3, the circle officer approves by T+5.</p>
    <div className="form-row"><label>Establishment ID<input name="establishment_id" required defaultValue="EST-DEMO-0001" /></label>
      <label>Contributory UANs (last month of default)<input name="contributory_uans" type="number" min="0" required /></label></div>
    <label>Note<textarea name="note" required minLength={10} /></label>
    <div className="actions"><button className="primary" disabled={busy} type="submit">Draft notice</button></div>
  </form>;
}

export function NoticeApproval({ caseId, role, state, busy, run }: { caseId: string; role: string; state: string; busy: boolean; run: Run }) {
  if (!((role === "fo.ss" && state === "NOTICE_DRAFTED") || (role === "fo.apfc" && state === "SS_ENDORSED"))) return null;
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget;
    run(() => command("POST", `${base}/cases/${caseId}/approvals`, { note: field(new FormData(form), "note") }),
      role === "fo.ss" ? "Endorsed to the circle officer." : "Approved: filed on e-Proceedings and allotted.", form);
  }
  return <form className="stack" aria-label="Approve damages notice" onSubmit={submit}>
    <label>Note<textarea name="note" required /></label>
    <div className="actions"><button className="primary" disabled={busy} type="submit">{role === "fo.ss" ? "Endorse" : "Approve and file"}</button></div>
  </form>;
}

export function LevyForm({ caseId, actions, busy, run, ask }: { caseId: string; actions: Action[]; busy: boolean; run: Run; ask: Ask }) {
  const noticed = (actions.find((a) => a.kind === "NOTICE_DRAFT")?.detail.demands ?? []) as NoticedDemand[];
  const passed = new Set(actions.filter((a) => a.kind === "ORDER").map((a) => String(a.detail.kind)));
  const kinds = (["14B", "7Q"] as const).filter((k) => !passed.has(k) && noticed.some((d) => d.kind === (k === "14B" ? "DAMAGES_14B" : "INTEREST_7Q")));
  async function submit(e: FormEvent<HTMLFormElement>, kind: "14B" | "7Q") {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const levies = noticed.filter((d) => d.kind === (kind === "14B" ? "DAMAGES_14B" : "INTEREST_7Q"))
      .map((d) => ({ demand_id: d.demand_id, amount_paise: Math.round(Number(f.get(d.demand_id)) * 100) }));
    const total = levies.reduce((s, l) => s + l.amount_paise, 0);
    const token = await ask({ action: "pass-order", resourceId: caseId, amountPaise: total, summary: `Pass the ${kind} order for ${rupees(total)}` });
    if (!token) return;
    run(() => command("POST", `${base}/cases/${caseId}/orders`, { kind, levies, reasoning: field(f, "reasoning"), ex_parte: f.has("ex_parte") },
      { stepUpToken: token }), `${kind} order passed; the auto-calculated demands are replaced.`, form);
  }
  return <>{kinds.map((kind) => <form key={kind} className="stack" aria-label={`Pass ${kind} order`} onSubmit={(e) => void submit(e, kind)}>
    <h3>{kind === "14B" ? "Damages under section 14B" : "Interest under section 7Q"}</h3>
    {noticed.filter((d) => d.kind === (kind === "14B" ? "DAMAGES_14B" : "INTEREST_7Q")).map((d) => <label key={d.demand_id}>
      {d.wage_month} · {d.days_late} days late · worked out {rupees(d.amount_paise)} (₹)
      <input name={d.demand_id} type="number" min="0" step="0.01" max={d.amount_paise / 100} defaultValue={d.amount_paise / 100} readOnly={kind === "7Q"} required /></label>)}
    {kind === "7Q" ? <p className="muted small">Interest is at the statutory rate and cannot be varied.</p> : <p className="muted small">Damages up to the amount worked out; record the reasons for any reduction.</p>}
    <label>Findings and reasons<textarea name="reasoning" required /></label>
    <label><input type="checkbox" name="ex_parte" /> Ex parte (only after due service, the employer absent)</label>
    <div className="actions"><button className="primary" disabled={busy} type="submit">Pass {kind} order</button></div>
  </form>)}</>;
}

export function AfterOrder({ caseId, rank, section, actions, busy, run, ask }:
  { caseId: string; rank: string; section: string; actions: Action[]; busy: boolean; run: Run; ask: Ask }) {
  const pending = [...actions].reverse().find((a) => a.kind === "APPLICATION" && a.detail.status === "PENDING");
  async function review(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const token = await ask({ action: "review-order", resourceId: caseId, summary: `Decide the review of ${caseId}` }); if (!token) return;
    run(() => command("POST", `${base}/cases/${caseId}/reviews-7b`, { ...(pending?.detail.kind === "REVIEW_7B" ? { application_id: pending.detail.application_id } : {}),
      view_by_rank: NEXT_HIGHER[rank], view_note: field(f, "view_note"), decision: field(f, "decision"), note: field(f, "note") }, { stepUpToken: token }),
      "Review decided.", form);
  }
  async function setAside(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const token = await ask({ action: "set-aside-order", resourceId: caseId, summary: `Decide the set-aside application in ${caseId}` }); if (!token) return;
    run(() => command("POST", `${base}/cases/${caseId}/set-asides`, { application_id: pending?.detail.application_id, decision: field(f, "decision"),
      note: field(f, "note") }, { stepUpToken: token }), "Application decided.", form);
  }
  async function escaped(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const token = await ask({ action: "escaped-assessment", resourceId: caseId, summary: `Reopen ${caseId} under 7C` }); if (!token) return;
    run(() => command("POST", `${base}/cases/${caseId}/escaped-assessments-7c`, { reason_type: field(f, "reason_type"), reason: field(f, "reason") },
      { stepUpToken: token }), "Reopened under 7C: a linked inquiry is registered.", form);
  }
  if (section === "14B" || section === "26B") return null;
  return <div className="stack">
    {pending?.detail.kind === "SET_ASIDE" ? <form className="stack" aria-label="Decide set-aside" onSubmit={(e) => void setAside(e)}>
      <h3>Application to set aside the ex-parte order</h3><p>{String(pending.detail.grounds)}: {String(pending.detail.text)}</p>
      <label>Decision<select name="decision"><option value="SET_ASIDE">Set aside — hear afresh</option><option value="REJECTED">Reject</option></select></label>
      <label>Note<textarea name="note" required /></label>
      <div className="actions"><button className="primary" disabled={busy} type="submit">Decide</button></div></form>
      : <form className="stack" aria-label="Review under 7B" onSubmit={(e) => void review(e)}>
        <h3>Review under section 7B {pending ? "— on the employer's application" : "— of your own motion"}</h3>
        {pending ? <p>{String(pending.detail.grounds)}: {String(pending.detail.text)}</p> : null}
        <label>View of the {NEXT_HIGHER[rank] ?? "next-higher officer"} (para 2.7.1)<textarea name="view_note" required /></label>
        <label>Decision<select name="decision"><option value="GRANTED">Grant — notice to the parties, then a fresh order</option><option value="REJECTED">Reject</option></select></label>
        <label>Note<textarea name="note" required /></label>
        <div className="actions"><button className="primary" disabled={busy} type="submit">Decide review</button></div></form>}
    <form className="stack" aria-label="Reopen under 7C" onSubmit={(e) => void escaped(e)}>
      <h3>Escaped amount (section 7C)</h3><p className="muted small">Within 5 years of the order; the employer is heard before any order.</p>
      <label>Ground<select name="reason_type"><option value="OMISSION_BY_EMPLOYER">The employer did not disclose fully and truly</option>
        <option value="INFORMATION_IN_POSSESSION">Information now in possession</option></select></label>
      <label>Reason<textarea name="reason" required /></label>
      <div className="actions"><button disabled={busy} type="submit">Reopen under 7C</button></div></form>
  </div>;
}

interface Due { case_id: string; diary_no: string; establishment_id: string; officer_rank: string; ordered_at: string; scrutiny_due: string; scrutinised: boolean; overdue: boolean }
export function ScrutinyList({ busy, run }: { busy: boolean; run: Run }) {
  const month = new Date().toISOString().slice(0, 7);
  const due = useQuery({ queryKey: ["scrutinies", month], retry: false, queryFn: () => api<Envelope<Due[]>>(`${base}/scrutinies?month=${month}`) });
  function submit(e: FormEvent<HTMLFormElement>, caseId: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    run(() => command("POST", `${base}/cases/${caseId}/scrutinies`, { observations: field(f, "observations"), direct_7c: f.has("direct_7c") }),
      "Scrutiny recorded.", form);
  }
  return <section className="card stack" aria-labelledby="scrutiny-heading">
    <h2 id="scrutiny-heading">Scrutiny of orders</h2>
    <p className="muted small">Orders passed this month by the officer next below you, to be scrutinised by the 15th of the following month (para 2.11).</p>
    {due.data && !due.data.data?.length ? <p className="muted">No order is due for your scrutiny.</p> : null}
    {due.data?.data?.map((d) => <article key={d.case_id} className="profile-card stack" aria-label={`Scrutiny ${d.diary_no}`}>
      <h3>{d.diary_no} · {d.establishment_id} <span className="state-pill">{d.scrutinised ? "Scrutinised" : `Due ${d.scrutiny_due}`}</span>
        {d.overdue ? <strong className="inquiry-overdue">Overdue</strong> : null}</h3>
      <p className="muted small">Order by the {d.officer_rank} on {new Date(d.ordered_at).toLocaleDateString("en-IN")}</p>
      {!d.scrutinised ? <form className="stack" onSubmit={(e) => submit(e, d.case_id)}>
        <label>Observations (standard proforma)<textarea name="observations" required /></label>
        <label><input type="checkbox" name="direct_7c" /> Direct a 7C inquiry for an escaped amount</label>
        <div className="actions"><button className="primary" disabled={busy} type="submit">Record scrutiny</button></div></form> : null}
    </article>)}
  </section>;
}
