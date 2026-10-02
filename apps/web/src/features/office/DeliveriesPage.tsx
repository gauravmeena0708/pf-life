import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime } from "../journeyB";
import { statusLabel } from "../statusLabel";
import "./DeliveriesPage.css";

interface Attempt { attempt: number; at: string; outcome: string; http_status: number | null; gateway_message_id: string | null; error: string | null }
interface Delivery { delivery_id: string; recipient_subject: string; channel: string; destination_masked: string; template: string; state: string; attempts: number; reason: string | null; updated_at: string; attempts_evidence: Attempt[] }
const states = ["FAILED", "QUEUED", "RETRYING", "DELIVERED", "SKIPPED"];

export function DeliveriesPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [state, setState] = useState("FAILED");
  const [open, setOpen] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const deliveries = useQuery({ queryKey: ["notification-deliveries", state], queryFn: () => api<Envelope<Delivery[]>>(`/api/v1/office/notification-deliveries${state ? `?state=${encodeURIComponent(state)}` : ""}`), retry: false });

  async function sendAgain(row: Delivery) {
    setBusy(row.delivery_id); setError(null); setNotice(null);
    try {
      await command("POST", `/api/v1/office/notification-deliveries/${encodeURIComponent(row.delivery_id)}/retries`);
      setNotice(`Delivery ${row.delivery_id} queued again.`);
      await qc.invalidateQueries({ queryKey: ["notification-deliveries"] });
    } catch (cause) { setError(cause); } finally { setBusy(null); }
  }

  return <section className="stack" aria-labelledby="deliveries-heading">
    <PageHeader id="deliveries-heading" eyebrow="Office · message gateway" title="SMS / e-mail deliveries" description="Delivery state and gateway attempts for member messages." current="SMS / e-mail deliveries" />
    <section className="card stack" aria-labelledby="delivery-list-heading"><h2 id="delivery-list-heading">Deliveries</h2>
      <label className="delivery-filter">State<select value={state} onChange={(e) => setState(e.target.value)}><option value="">All states</option>{states.map((code) => <option key={code} value={code}>{statusLabel(code, t)}</option>)}</select></label>
      <ProblemMessage error={deliveries.error ?? error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
      {deliveries.isLoading ? <p role="status">Loading deliveries…</p> : null}
      {deliveries.data?.data.length === 0 ? <p className="muted">No deliveries match this state.</p> : null}
      {deliveries.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Member</th><th scope="col">Channel</th><th scope="col">Destination</th><th scope="col">Template</th><th scope="col">State</th><th scope="col">Attempts</th><th scope="col">Reason</th><th scope="col">Last update</th><th scope="col">Actions</th></tr></thead><tbody>
        {deliveries.data.data.map((row) => <DeliveryRows key={row.delivery_id} row={row} expanded={open.includes(row.delivery_id)} toggle={() => setOpen(open.includes(row.delivery_id) ? open.filter((id) => id !== row.delivery_id) : [...open, row.delivery_id])} canRetry={session.data?.stakeholder === "fo.pro" && row.state === "FAILED"} busy={busy === row.delivery_id} retry={() => void sendAgain(row)} language={i18n.language} t={t} />)}
      </tbody></table></div> : null}
    </section>
  </section>;
}

function DeliveryRows({ row, expanded, toggle, canRetry, busy, retry, language, t }: { row: Delivery; expanded: boolean; toggle: () => void; canRetry: boolean; busy: boolean; retry: () => void; language: string; t: ReturnType<typeof useTranslation>["t"] }) {
  return <><tr><td>{row.recipient_subject}</td><td>{statusLabel(row.channel, t)}</td><td>{row.destination_masked}</td><td><code>{row.template}</code></td><td><span className="state-pill">{statusLabel(row.state, t)}</span></td><td>{row.attempts}</td><td>{row.reason || "—"}</td><td>{dateTime(row.updated_at, language)}</td><td className="delivery-actions"><button type="button" aria-expanded={expanded} aria-controls={`attempts-${row.delivery_id}`} onClick={toggle}>Attempts evidence</button>{canRetry ? <button type="button" disabled={busy} onClick={retry}>Send again</button> : null}</td></tr>
    {expanded ? <tr id={`attempts-${row.delivery_id}`}><td colSpan={9}><div className="delivery-evidence"><strong>Gateway attempts</strong>{row.attempts_evidence.length ? <table><thead><tr><th scope="col">Attempt</th><th scope="col">Time</th><th scope="col">Outcome</th><th scope="col">HTTP status</th><th scope="col">Gateway message ID</th><th scope="col">Error</th></tr></thead><tbody>{row.attempts_evidence.map((attempt) => <tr key={attempt.attempt}><td>{attempt.attempt}</td><td>{dateTime(attempt.at, language)}</td><td>{statusLabel(attempt.outcome, t)}</td><td>{attempt.http_status ?? "—"}</td><td>{attempt.gateway_message_id ?? "—"}</td><td>{attempt.error ?? "—"}</td></tr>)}</tbody></table> : <p>No attempts recorded.</p>}</div></td></tr> : null}</>;
}
