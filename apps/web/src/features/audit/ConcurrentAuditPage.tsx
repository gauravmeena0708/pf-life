import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { InternalParas } from "./InternalParas";
import { IssueTrackerRequests } from "../ndc/IssueTrackerPage";

interface ExtractItem {
  event_id: string; occurred_at: string; event_type: string; reference: string | null; amount_paise: number | null;
  office_id: string | null; flags: string[]; correlation_id: string; hash: string;
}
interface Extract { day: string; items: ExtractItem[]; flag_counts: Record<string, number>; events_scanned: number; note: string }
interface Alert {
  alert_id: string; office_id: string; zone_id: string; reference: string; event_id: string | null; flags: string[]; finding: string;
  state: "OPEN" | "REPLIED" | "CLOSED"; due_by: string; raised_at: string; overdue: boolean;
  reply: { reply: string; action_taken: string; by: string; at: string; late: boolean } | null;
}
export function ConcurrentAuditPage() {
  const qc = useQueryClient();
  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const auditor = session.data?.stakeholder === "zo.rpfc1_audit"; const oic = session.data?.stakeholder === "fo.oic";
  const extracts = useQuery({ queryKey: ["concurrent-extracts", day], enabled: auditor && /^\d{4}-\d{2}-\d{2}$/.test(day), retry: false,
    queryFn: () => api<Envelope<Extract>>(`/api/v1/audit/concurrent/extracts?day=${encodeURIComponent(day)}`) });
  const alerts = useQuery({ queryKey: ["concurrent-alerts"], enabled: auditor || oic, retry: false,
    queryFn: () => api<Envelope<Alert[]>>("/api/v1/audit/concurrent/alerts") });
  async function submit(e: FormEvent<HTMLFormElement>, item: ExtractItem | Alert) {
    e.preventDefault(); if (busy) return;
    const form = e.currentTarget; const f = new FormData(form); const text = (name: string) => String(f.get(name) ?? "").trim();
    setBusy(true); setError(null); setNotice(null);
    try {
      if ("alert_id" in item) {
        if (!oic || item.state !== "OPEN") return;
        const reply = text("reply"); const action_taken = text("action_taken");
        if (reply.length < 10 || action_taken.length < 5) throw new Error("Enter a reply of at least 10 characters and action taken of at least 5 characters.");
        await command("POST", `/api/v1/audit/concurrent/alerts/${encodeURIComponent(item.alert_id)}/replies`, { reply, action_taken });
        setNotice(`Reply recorded for ${item.alert_id}.`);
      } else {
        if (!auditor) return;
        const office_id = text("office_id"); const reference = text("reference"); const finding = text("finding");
        if (office_id.length < 3 || reference.length < 3 || finding.length < 10) throw new Error("Enter an office, reference and finding of at least 10 characters.");
        const result = await command<Envelope<Alert>>("POST", "/api/v1/audit/concurrent/alerts", { office_id, reference, event_id: item.event_id, flags: item.flags, finding });
        setNotice(`Alert ${result.data.alert_id} raised.`);
      }
      form.reset(); await qc.invalidateQueries({ queryKey: ["concurrent-alerts"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  const extract = extracts.data?.data; const heading = oic ? "audit-alerts-heading" : "alerts-heading";
  return <section className="stack" aria-labelledby="concurrent-audit-heading">
    <PageHeader id="concurrent-audit-heading" eyebrow={oic ? "Office in charge" : "Concurrent Audit Cell"} title="Concurrent audit"
      description={oic ? "Reply to audit alerts and raise requests supported by an order." : "Review daily audit extracts and raise findings for the responsible office."} current="Concurrent audit" />
    <ProblemMessage error={error ?? session.error ?? extracts.error ?? alerts.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !auditor && !oic ? <p className="pending-notice">This service is available to the Concurrent Audit Cell and office in charge.</p> : null}
    {auditor ? <section className="card stack" aria-labelledby="extract-heading"><h2 id="extract-heading">Daily audit extract</h2>
      <label>Extract day<input type="date" required value={day} onChange={(e) => setDay(e.target.value)} /></label>
      {extracts.isFetching ? <p role="status">Loading extract…</p> : null}
      {extract ? <><p>{extract.day} · {extract.events_scanned} events scanned</p><p>{extract.note}</p>
        <ul aria-label="Flag counts">{Object.entries(extract.flag_counts).map(([flag, count]) => <li key={flag}>{flag}: {count}</li>)}</ul>
        {extract.items.map((item) => <article className="card stack" key={item.event_id}><h3>{item.event_type} · {item.reference ?? item.event_id}</h3>
          <dl className="kv"><dt>Event</dt><dd>{item.event_id}</dd><dt>Occurred at</dt><dd>{item.occurred_at}</dd>
            <dt>Amount</dt><dd>{rupees(item.amount_paise)}</dd><dt>Office</dt><dd>{item.office_id ?? "Not recorded"}</dd>
            <dt>Flags</dt><dd>{item.flags.join(", ")}</dd><dt>Correlation</dt><dd>{item.correlation_id}</dd><dt>Hash</dt><dd>{item.hash}</dd></dl>
          <form className="stack" aria-label={`Raise alert for ${item.event_id}`} onSubmit={(e) => void submit(e, item)}>
            <fieldset className="stack" disabled={busy}><legend>Raise alert</legend>
              <label>Office ID<input name="office_id" required defaultValue={item.office_id ?? "RO-DEMO-01"} /></label>
              <label>Reference<input name="reference" required minLength={3} maxLength={80} defaultValue={item.reference ?? item.event_id} /></label>
              <label>Finding<textarea name="finding" required minLength={10} maxLength={4000} /></label>
              <div className="actions"><button className="primary" type="submit">Raise alert</button></div>
            </fieldset>
          </form>
        </article>)}
        {!extract.items.length ? <p className="muted">No flagged events for this day.</p> : null}
      </> : null}
    </section> : null}
    {auditor || oic ? <section className="card stack" aria-labelledby={heading}><h2 id={heading}>Audit alerts</h2>
      {alerts.isLoading ? <p role="status">Loading alerts…</p> : null}
      {alerts.data?.data.map((alert) => <article className="card stack" key={alert.alert_id}><h3>{alert.alert_id} · {alert.reference}</h3>
        <p>{alert.office_id} · Zone {alert.zone_id} · {alert.state} · {alert.overdue ? "Overdue" : "Not overdue"}</p>
        <p>Raised {alert.raised_at} · Reply due {alert.due_by}</p><p>Event: {alert.event_id ?? "—"} · Flags: {alert.flags.join(", ") || "None"}</p><p>{alert.finding}</p>
        {alert.reply ? <dl className="kv"><dt>Reply</dt><dd>{alert.reply.reply}</dd><dt>Action taken</dt><dd>{alert.reply.action_taken}</dd>
          <dt>Replied by</dt><dd>{alert.reply.by}</dd><dt>Replied at</dt><dd>{alert.reply.at}</dd><dt>Late reply</dt><dd>{alert.reply.late ? "Yes" : "No"}</dd></dl> : null}
        {oic && alert.state === "OPEN" ? <form className="stack" aria-label={`Reply to alert ${alert.alert_id}`} onSubmit={(e) => void submit(e, alert)}>
          <fieldset className="stack" disabled={busy}><legend>Office reply</legend>
            <label>Reply<textarea name="reply" required minLength={10} maxLength={4000} /></label>
            <label>Action taken<textarea name="action_taken" required minLength={5} maxLength={1000} /></label>
            <div className="actions"><button className="primary" type="submit">Send reply</button></div>
          </fieldset>
        </form> : null}
      </article>)}
      {alerts.data && !alerts.data.data.length ? <p className="muted">No audit alerts.</p> : null}
    </section> : null}
    {oic ? <InternalParas role="fo.oic" /> : null}
    {oic ? <IssueTrackerRequests /> : null}
  </section>;
}
