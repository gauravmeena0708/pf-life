import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface Signal {
  signal_id: string; subject_ref: string; detection_type: string; rule_version: string; evidence_refs: string[];
  explanation: string; context: { shared_device?: boolean; subjects_on_device?: number; note?: string };
  status: string; review_note: string | null; reviewed_at: string | null; created_at: string | null; advisory_only: boolean;
}
interface Signals {
  rule_version: string; signals: Signal[];
  shared_devices_not_signals: { device: string; subjects: number; note: string }[];
}

const OPEN = ["OPEN", "NEEDS_MORE_EVIDENCE"];

/** CAIU review of advisory risk signals (Journey D2–D4). A review records a human judgement; nothing else happens. */
export function RiskSignalsPage() {
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [referring, setReferring] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const data = useQuery({ queryKey: ["risk-signals"], queryFn: () => api<Envelope<Signals>>("/api/v1/caiu/synthetic-risk-signals"),
    retry: false, refetchInterval: 5000 });
  const d = data.data?.data;

  async function review(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setError(null); setNotice(null);
    try {
      await command("POST", `/api/v1/caiu/synthetic-risk-signals/${id}/reviews`, { outcome: form.get("outcome"), note: String(form.get("note")).trim() });
      setNotice(`Review recorded for ${id}. No automatic action was taken.`);
      await qc.invalidateQueries({ queryKey: ["risk-signals"] });
    } catch (cause) { setError(cause); }
  }

  async function refer(e: FormEvent<HTMLFormElement>, id: string) {
    e.preventDefault(); if (busy) return;
    const form = e.currentTarget;
    const values = new FormData(form);
    const read = (name: string) => String(values.get(name) ?? "").trim();
    const complainant = read("complainant");
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = await command<Envelope<{ vcn: string }>>("POST", "/api/v1/vigilance/referrals", {
        source: "CAIU_SIGNAL", source_ref: id, subject_type: read("subject_type"),
        subject_ref: read("subject_ref"), office_id: read("office_id"), allegation: read("allegation"),
        evidence: [{ kind: "RISK_SIGNAL", ref: id }], ...(complainant ? { complainant: { name: complainant } } : {}),
      });
      setNotice(`Referred to vigilance as ${result.data.vcn}.`);
      setReferring(null); form.reset();
      await qc.invalidateQueries({ queryKey: ["risk-signals"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return (
    <section className="stack" aria-labelledby="signals-heading">
      <PageHeader id="signals-heading" eyebrow="CAIU · Journey D" title="Advisory risk signals"
        description={`Explainable, versioned rules (${d?.rule_version ?? "…"}). A signal asks for a human review; it never blocks, accuses or penalises.`}
        current="Risk signals" />
      <ProblemMessage error={data.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {d?.signals.length === 0 ? <p className="card muted">No signals.</p> : null}
      {d && d.signals.length > 0 && !d.signals.some((s) => OPEN.includes(s.status)) ? <p className="card muted">No signal is waiting for review.</p> : null}
      {d?.signals.filter((s) => OPEN.includes(s.status)).map((s) => (
        <article key={s.signal_id} className="card stack" aria-labelledby={`sig-${s.signal_id}`}>
          <div className="section-heading">
            <div><p className="eyebrow">{s.detection_type}</p><h2 id={`sig-${s.signal_id}`}>{s.signal_id}</h2></div>
            <span className="state-pill">{s.status.replaceAll("_", " ").toLowerCase()}</span>
          </div>
          <p>{s.explanation}</p>
          <dl className="kv">
            <dt>Account</dt><dd><code>{s.subject_ref}</code></dd>
            <dt>Evidence</dt><dd>{s.evidence_refs.map((r) => <code key={r}>{r.slice(0, 8)} </code>)}<span className="muted small"> (security event IDs; trace them in the audit log)</span></dd>
            <dt>Rule version</dt><dd>{s.rule_version}</dd>
          </dl>
          {s.context.shared_device ? <p className="demo-tip"><strong>Context, not evidence:</strong> {s.context.note}</p> : null}
          {s.review_note ? <p className="muted"><strong>Review:</strong> {s.review_note}</p> : null}
          {["OPEN", "NEEDS_MORE_EVIDENCE"].includes(s.status) ? (
            <form className="stack" onSubmit={(e) => void review(e, s.signal_id)}>
              <fieldset className="case-options"><legend>Outcome</legend>
                {[["needs-more-evidence", "Needs more evidence"], ["benign", "Benign — legitimate activity"], ["confirmed", "Confirmed — refer for follow-up"]].map(([v, label]) => (
                  <label className="check-row" key={v}><input type="radio" name="outcome" value={v} required defaultChecked={v === "needs-more-evidence"} />{label}</label>
                ))}
              </fieldset>
              <label>Reasoning (kept with the review)<textarea name="note" required minLength={10} maxLength={2000} /></label>
              <div className="actions"><button type="submit" className="primary">Record review</button></div>
            </form>
          ) : null}
        </article>
      ))}
      {d?.signals.some((s) => !OPEN.includes(s.status)) ? (
        <details className="card filter-panel">
          <summary>Reviewed signals ({d.signals.filter((s) => !OPEN.includes(s.status)).length})</summary>
          <div className="table-scroll"><table>
            <thead><tr><th scope="col">Signal</th><th scope="col">Rule</th><th scope="col">Outcome</th><th scope="col">Reviewed</th><th scope="col">Reasoning</th><th scope="col">Action</th></tr></thead>
            <tbody>{d.signals.filter((s) => !OPEN.includes(s.status)).map((s) => (
              <tr key={s.signal_id}><td><code>{s.signal_id}</code></td><td>{s.detection_type}</td><td>{s.status.toLowerCase()}</td>
                <td>{s.reviewed_at ? new Date(s.reviewed_at).toLocaleString("en-IN") : "—"}</td><td>{s.review_note}</td>
                <td>{s.status === "CONFIRMED" ? <button type="button" onClick={() => setReferring(referring === s.signal_id ? null : s.signal_id)}>Refer to vigilance</button> : "—"}</td></tr>
            ))}</tbody>
          </table></div>
          {d.signals.filter((s) => s.status === "CONFIRMED" && referring === s.signal_id).map((s) => <form key={s.signal_id} className="stack" aria-label={`Refer signal ${s.signal_id} to vigilance`} onSubmit={(e) => void refer(e, s.signal_id)}>
            <fieldset className="stack" disabled={busy}><legend>Vigilance referral · {s.signal_id}</legend>
              <label>Subject type<select name="subject_type" required><option value="MEMBER">Member</option><option value="ESTABLISHMENT">Establishment</option><option value="OFFICIAL">Official</option></select></label>
              <label>Subject reference<input name="subject_ref" defaultValue={s.subject_ref} required minLength={3} maxLength={80} /></label>
              <label>Office ID<input name="office_id" defaultValue="RO-DEMO-01" required minLength={3} maxLength={40} /></label>
              <label>Allegation<textarea name="allegation" required minLength={20} maxLength={4000} /></label>
              <label>Complainant name (optional)<input name="complainant" minLength={2} maxLength={120} /></label>
              <div className="actions"><button type="submit" className="primary">Submit referral</button></div>
            </fieldset>
          </form>)}
        </details>
      ) : null}
      {d?.shared_devices_not_signals.length ? (
        <section className="card stack" aria-labelledby="shared-heading">
          <h2 id="shared-heading">Shared devices (not signals)</h2>
          <p className="muted">A device used by several members is normal — for example a Common Service Centre kiosk or a family phone. It is shown here for context only and never raises a signal by itself.</p>
          <ul className="lookup-results">{d.shared_devices_not_signals.map((x) => <li key={x.device}><strong>Device {x.device}</strong><span>{x.subjects} members</span></li>)}</ul>
        </section>
      ) : null}
    </section>
  );
}
