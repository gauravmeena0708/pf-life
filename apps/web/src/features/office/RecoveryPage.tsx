import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import "./InquiriesPage.css";

/** The Recovery Officer's certificates (Recovery Manual): the demand notice and its 15 days, collections, attachment and sale,
 *  a receiver, arrest only after a notice to show cause — records, no property or warrant is real; the RPFC grants instalments. */
const base = "/api/v1/office/recovery";
interface Action { kind: string; at: string; detail: Record<string, unknown> }
export interface RecoveryCase {
  recovery_case_id: string; establishment_id: string; inquiry_case_id: string | null; certificate_no: string; amount_paise: number;
  realised_paise: number; outstanding_paise: number; state: string; pay_by: string | null; stayed: boolean; actions: Action[];
}
export const RECOVERY_STATE: Record<string, string> = { CERTIFIED: "Certificate received — notice due", NOTICE_SERVED: "Demand notice served",
  IN_EXECUTION: "In execution", INSTALMENTS: "Instalments running", CLOSED: "Satisfied — closed" };
const field = (f: FormData, name: string) => String(f.get(name) ?? "").trim();
const toPaise = (f: FormData, name: string) => Math.round(Number(f.get(name) || 0) * 100);
const when = (iso: unknown) => (iso ? new Date(String(iso)).toLocaleDateString("en-IN") : "—");

export function RecoveryPage() {
  const qc = useQueryClient(); const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder ?? "";
  const list = useQuery({ queryKey: ["recovery-cases"], enabled: !!role, retry: false, queryFn: () => api<Envelope<RecoveryCase[]>>(`${base}/cases`) });
  async function run(work: () => Promise<unknown>, ok: string, form?: HTMLFormElement) {
    setBusy(true); setError(null); setNotice("");
    try { await work(); form?.reset(); setNotice(ok); await qc.invalidateQueries({ queryKey: ["recovery-cases"] }); } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  async function guarded(action: string, id: string, summary: string, work: (token: string) => Promise<unknown>, ok: string, form: HTMLFormElement, amountPaise?: number) {
    const token = await stepUp.ask({ action, resourceId: id, summary, ...(amountPaise ? { amountPaise } : {}) }); if (!token) return;
    void run(() => work(token), ok, form);
  }
  function attach(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    const body = { kind: field(f, "kind"), description: field(f, "description"), value_paise: toPaise(f, "value"), ...(field(f, "urgent_reason") ? { urgent_reason: field(f, "urgent_reason") } : {}) };
    void guarded("attach-property", id, `Attach property in ${id}`, (token) => command("POST", `${base}/${id}/attachments`, body, { stepUpToken: token }), "Attachment recorded.", form);
  }
  function sell(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); const price = toPaise(f, "sale_price");
    const body = { attachment_id: field(f, "attachment_id"), reserve_price_paise: toPaise(f, "reserve_price"), sale_price_paise: price, buyer: field(f, "buyer") };
    void guarded("sell-property", id, `Record the sale for ${rupees(price)}`, (token) => command("POST", `${base}/${id}/sales`, body, { stepUpToken: token }), "Sale recorded; the proceeds are realised.", form, price);
  }
  function receiver(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void guarded("appoint-receiver", id, `Appoint a receiver in ${id}`, (token) => command("POST", `${base}/${id}/receivers`,
      { over: field(f, "over"), receiver: field(f, "receiver"), note: field(f, "note") }, { stepUpToken: token }), "Receiver appointed.", form);
  }
  function arrest(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); const step = field(f, "step");
    const ground = { WARRANT: field(f, "warrant_ground"), DETENTION_ORDER: field(f, "detention_ground"), RELEASED: field(f, "release_ground") }[step];
    const body = { step, reasons: field(f, "reasons"), ...(step === "SHOW_CAUSE" ? { hearing_on: field(f, "hearing_on") } : { ground }) };
    void guarded("arrest-defaulter", id, `${step} in ${id}`, (token) => command("POST", `${base}/${id}/arrest-warrants`, body, { stepUpToken: token }), "Recorded.", form);
  }
  function pay(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(() => command("POST", `${base}/${id}/payments`, { amount_paise: toPaise(f, "amount"), reference: field(f, "reference"), mode: field(f, "mode") }), "Payment realised.", form);
  }
  function instalments(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(() => command("POST", `${base}/${id}/instalments`, { count: Number(f.get("count")), first_due: field(f, "first_due"), note: field(f, "note"),
      bank_guarantee_paise: toPaise(f, "guarantee"), bank_guarantee_ref: field(f, "guarantee_ref") }), "Instalments granted.", form);
  }
  function defaulted(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form);
    void run(() => command("POST", `${base}/${id}/instalment-defaults`, { missed: field(f, "missed") }), "Instalment facility withdrawn; recovery resumes.", form);
  }

  return <section className="stack" aria-labelledby="recovery-heading">
    <PageHeader id="recovery-heading" eyebrow="Recovery" title="Recovery certificates" current="Recovery"
      description="Arrears certified for recovery under section 8B: the demand notice, then attachment and sale, a receiver or arrest — records in this demonstration (Recovery Manual)." />
    <ProblemMessage error={list.error} /><ProblemMessage error={error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {list.data && !list.data.data?.length ? <p className="muted">No recovery certificates.</p> : null}
    {list.data?.data?.map((c) => {
      const attachments = c.actions.filter((a) => a.kind === "ATTACHMENT" && !c.actions.some((s) => s.kind === "SALE" && s.detail.attachment_id === a.detail.attachment_id));
      const open = c.state !== "CLOSED";
      return <article key={c.recovery_case_id} className="card stack" aria-label={`Certificate ${c.certificate_no}`}>
        <h2>{c.certificate_no} · {c.establishment_id} <span className="state-pill">{RECOVERY_STATE[c.state] ?? c.state}</span>
          {c.stayed ? <strong className="inquiry-overdue">Stayed by a court</strong> : null}</h2>
        <p>Certified {rupees(c.amount_paise)} · realised {rupees(c.realised_paise)} · outstanding <strong>{rupees(c.outstanding_paise)}</strong>
          {c.pay_by ? ` · notice expires ${when(c.pay_by)}` : ""}</p>
        <ol className="inquiry-steps">{c.actions.map((a, i) => <li key={i}><strong>{a.kind}</strong> · {when(a.at)}
          {a.kind === "REALISATION" ? ` — ${rupees(Number(a.detail.amount_paise))} by ${String(a.detail.mode)}` : ""}
          {a.kind === "ATTACHMENT" ? ` — ${String(a.detail.attachment_id)}: ${String(a.detail.description)}` : ""}
          {a.kind === "ARREST" ? ` — ${String(a.detail.step)}${a.detail.ground ? ` (${String(a.detail.ground)})` : ""}` : ""}</li>)}</ol>
        {role === "fo.recovery_officer" && c.state === "CERTIFIED" ? <div className="actions"><button className="primary" disabled={busy} type="button"
          onClick={() => void run(() => command("POST", `${base}/${c.recovery_case_id}/demand-notices`), "Demand notice (EPFCP-1) served: 15 days to pay.")}>Serve demand notice (EPFCP-1)</button></div> : null}
        {role === "fo.recovery_officer" && open ? <div className="activity-columns">
          <form className="stack" aria-label={`Payment ${c.certificate_no}`} onSubmit={(e) => pay(e, c.recovery_case_id)}><h3>Payment received</h3>
            <label>Amount (₹)<input name="amount" type="number" min="0.01" step="0.01" required /></label><label>Reference (TRRN)<input name="reference" required /></label>
            <label>As<select name="mode"><option value="DIRECT">Payment</option><option value="INSTALMENT">Instalment</option></select></label>
            <div className="actions"><button disabled={busy} type="submit">Record payment</button></div></form>
          <form className="stack" aria-label={`Attach ${c.certificate_no}`} onSubmit={(e) => attach(e, c.recovery_case_id)}><h3>Attach property</h3>
            <label>Kind<select name="kind"><option value="MOVABLE">Movable</option><option value="IMMOVABLE">Immovable</option><option value="DEBTS_SHARES">Debts or shares</option></select></label>
            <label>Description<input name="description" required /></label><label>Value (₹)<input name="value" type="number" min="1" required /></label>
            <label>Reason it cannot wait for the notice period (if within it)<input name="urgent_reason" /></label>
            <div className="actions"><button disabled={busy} type="submit">Attach</button></div></form>
          {attachments.length ? <form className="stack" aria-label={`Sale ${c.certificate_no}`} onSubmit={(e) => sell(e, c.recovery_case_id)}><h3>Sale of attached property</h3>
            <label>Property<select name="attachment_id">{attachments.map((a) => <option key={String(a.detail.attachment_id)} value={String(a.detail.attachment_id)}>{String(a.detail.attachment_id)} — {String(a.detail.description)}</option>)}</select></label>
            <label>Reserve price (₹)<input name="reserve_price" type="number" min="1" required /></label><label>Sale price (₹)<input name="sale_price" type="number" min="1" required /></label>
            <label>Buyer<input name="buyer" required /></label>
            <div className="actions"><button disabled={busy} type="submit">Record sale</button></div></form> : null}
          <form className="stack" aria-label={`Receiver ${c.certificate_no}`} onSubmit={(e) => receiver(e, c.recovery_case_id)}><h3>Receiver</h3>
            <label>Over<select name="over"><option value="BUSINESS">The business</option><option value="IMMOVABLE">Immovable property</option></select></label>
            <label>Receiver<input name="receiver" required /></label><label>Note<input name="note" required /></label>
            <div className="actions"><button disabled={busy} type="submit">Appoint</button></div></form>
          <form className="stack" aria-label={`Arrest ${c.certificate_no}`} onSubmit={(e) => arrest(e, c.recovery_case_id)}><h3>Arrest and detention</h3>
            <p className="muted small">A notice to show cause (EPFCP-25) and a hearing first; detention only for a dishonest transfer of property, or the means to pay and a refusal.</p>
            <label>Step<select name="step"><option value="SHOW_CAUSE">Notice to show cause</option><option value="WARRANT">Warrant of arrest</option>
              <option value="DETENTION_ORDER">Detention order</option><option value="RELEASED">Release</option></select></label>
            <label>Hearing on (notice)<input name="hearing_on" type="date" /></label>
            <label>Warrant ground<select name="warrant_ground"><option value="NON_APPEARANCE">Did not appear</option><option value="LIKELY_TO_ABSCOND">Likely to abscond</option></select></label>
            <label>Detention ground<select name="detention_ground"><option value="MEANS_BUT_REFUSES">Has the means, refuses to pay</option><option value="DISHONEST_TRANSFER">Transferred property dishonestly</option></select></label>
            <label>Release because<select name="release_ground"><option value="PAID">Paid</option><option value="SECURITY">Security furnished</option><option value="PERIOD_OVER">Period over</option></select></label>
            <label>Reasons<textarea name="reasons" required /></label>
            <div className="actions"><button disabled={busy} type="submit">Record</button></div></form>
        </div> : null}
        {role === "fo.recovery_officer" && c.state === "INSTALMENTS" ? <form className="stack" aria-label={`Default ${c.certificate_no}`}
          onSubmit={(e) => defaulted(e, c.recovery_case_id)}><h3>Instalment missed</h3>
          <p className="muted small">A missed instalment, or the current dues unpaid, withdraws the facility without notice.</p>
          <label>What was missed<input name="missed" required /></label>
          <div className="actions"><button disabled={busy} type="submit">Withdraw the facility</button></div></form> : null}
        {role === "fo.oic" && open && c.state !== "INSTALMENTS" ? <form className="stack" aria-label={`Instalments ${c.certificate_no}`} onSubmit={(e) => instalments(e, c.recovery_case_id)}>
          <h3>Grant instalments</h3>
          <p className="muted small">Up to 36 within your power by the arrears (RPFC-II ₹10 lakh, RPFC-I ₹25 lakh); above it, the zone (₹50 lakh) or
            Head Office, and more than 36 (at most 72) only Head Office. Each instalment is paid with that month&apos;s 7Q interest and the current
            dues; a revolving bank guarantee of one instalment (six beyond 36) is needed.</p>
          <div className="form-row"><label>Number<input name="count" type="number" min="2" max="72" required /></label>
            <label>First due<input name="first_due" type="date" required /></label></div>
          <div className="form-row"><label>Bank guarantee (₹)<input name="guarantee" type="number" min="0" step="0.01" required /></label>
            <label>Guarantee reference<input name="guarantee_ref" required /></label></div><label>Note<textarea name="note" required /></label>
          <div className="actions"><button disabled={busy} type="submit">Grant</button></div></form> : null}
      </article>;
    })}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
