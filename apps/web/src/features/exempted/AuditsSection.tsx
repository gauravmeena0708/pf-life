import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";

interface Audit { audit_id: string; financial_year: string; status: string; opinion: string; due_on: string; late_days: number; closing_corpus_paise: number }
const fields = [["opening_corpus", "Opening corpus"], ["contributions", "Contributions"], ["interest_credited", "Interest credited"], ["claims_paid", "Claims paid"], ["other", "Other (+/−)"], ["closing_corpus", "Closing corpus"]] as const;
const toPaise = (value: FormDataEntryValue | null) => Math.round(Number(value || 0) * 100);
export function AuditsSection({ estId }: { estId?: string }) {
  const { t } = useTranslation(); const qc = useQueryClient(); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const [amounts, setAmounts] = useState<Record<string, number>>({});
  const path = estId ? `/api/v1/office/exempted/${encodeURIComponent(estId)}/audits` : "/api/v1/exempted/me/audits";
  const audits = useQuery({ queryKey: ["trust-audits", path], queryFn: () => api<Envelope<Audit[]>>(path), retry: false });
  const expected = Math.round(((amounts.opening_corpus || 0) + (amounts.contributions || 0) + (amounts.interest_credited || 0) - (amounts.claims_paid || 0) + (amounts.other || 0)) * 100);
  const closing = Math.round((amounts.closing_corpus || 0) * 100);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (expected !== closing) { setError(new Error("Closing corpus does not balance.")); return; }
    const f = new FormData(event.currentTarget); const opinion = String(f.get("opinion")); const observations = String(f.get("observations") || "").trim();
    if (opinion !== "UNQUALIFIED" && !observations) { setError(new Error("Observations are required for this opinion.")); return; }
    const body = { financial_year: String(f.get("financial_year")), auditor_name: String(f.get("auditor_name")).trim(), auditor_registration: String(f.get("auditor_registration")).trim(),
      ...Object.fromEntries(fields.map(([key]) => [`${key}_paise`, toPaise(f.get(key))])), opinion, observations: observations || null, revised: f.has("revised") };
    setBusy(true); setError(null); setNotice("");
    try { await command("POST", path, body); setNotice("Annual audited accounts filed."); await qc.invalidateQueries({ queryKey: ["trust-audits", path] }); }
    catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="annual-audits-heading"><h2 id="annual-audits-heading">Annual audited accounts</h2>
    <ProblemMessage error={error ?? audits.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {audits.isLoading ? <p role="status">Loading audits…</p> : null}
    {audits.data?.data.length === 0 ? <p className="muted">No annual audits filed.</p> : null}
    {audits.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Financial year</th><th scope="col">Due date</th><th scope="col">Late days</th><th scope="col">Opinion</th><th scope="col">Closing corpus</th><th scope="col">Status</th></tr></thead><tbody>
      {audits.data.data.map((item) => <tr key={item.audit_id}><th scope="row">{item.financial_year}</th><td>{item.due_on}</td><td>{item.late_days}</td><td>{statusLabel(item.opinion, t)}</td><td>{rupees(item.closing_corpus_paise)}</td><td>{statusLabel(item.status, t)}</td></tr>)}
    </tbody></table></div> : null}
    {!estId ? <form className="stack" aria-label="File annual audited accounts" onSubmit={(e) => void submit(e)}><div className="form-row">
      <label>Financial year (YYYY-YY)<input name="financial_year" pattern="[0-9]{4}-[0-9]{2}" placeholder="2024-25" required /></label>
      <label>Auditor<input name="auditor_name" required /></label><label>Auditor registration<input name="auditor_registration" required /></label></div>
      <div className="form-row">{fields.map(([key, label]) => <label key={key}>{label} (₹)<input name={key} type="number" min={key === "other" ? undefined : "0"} step="0.01" defaultValue="0" required onChange={(e) => setAmounts((old) => ({ ...old, [key]: Number(e.target.value) }))} /></label>)}</div>
      <p role="status" aria-live="polite">Expected closing corpus: {rupees(expected)} · {expected === closing ? "Balanced" : "Does not balance"}</p>
      <label>Auditor opinion<select name="opinion"><option value="UNQUALIFIED">{statusLabel("UNQUALIFIED", t)}</option><option value="QUALIFIED">{statusLabel("QUALIFIED", t)}</option><option value="ADVERSE">{statusLabel("ADVERSE", t)}</option></select></label>
      <label>Observations<textarea name="observations" /></label><label><input name="revised" type="checkbox" /> Revise current audit for this year</label>
      <button className="primary" type="submit" disabled={busy || expected !== closing}>File annual audit</button></form> : null}
  </section>;
}
