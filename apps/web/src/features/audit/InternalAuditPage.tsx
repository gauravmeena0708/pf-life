import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import type { InternalPara } from "./InternalParas";

const categories = ["CLAIMS", "ACCOUNTS", "COMPLIANCE", "PENSION", "ADMINISTRATION", "IT"];
export function InternalAuditPage() {
  const { t } = useTranslation(); const qc = useQueryClient();
  const [reportId, setReportId] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState("");
  const paras = useQuery({ queryKey: ["internal-paras"], queryFn: () => api<Envelope<InternalPara[]>>( "/api/v1/audit/internal/paras"), retry: false });
  async function submit(e: FormEvent<HTMLFormElement>, kind: "report" | "para") {
    e.preventDefault(); if (busy) return; const form = e.currentTarget; const f = new FormData(form); const value = (key: string) => String(f.get(key) ?? "").trim();
    setBusy(true); setError(null); setNotice("");
    try {
      if (kind === "report") {
        const result = await command<Envelope<{ report_id: string }>>( "POST", "/api/v1/audit/internal/reports", { office_id: value("office_id"), period_from: value("period_from"), period_to: value("period_to"), scope: value("scope") });
        setReportId(result.data.report_id); setNotice(`Report ${result.data.report_id} created. Add its paras below.`);
      } else {
        const amount = value("amount_at_risk"); const paise = Math.round(Number(amount) * 100);
        if (!Number.isFinite(paise) || paise < 0 || !/^\d+(\.\d{1,2})?$/.test(amount)) throw new Error("Enter a valid rupee amount with up to two decimal places.");
        await command("POST", `/api/v1/audit/internal/reports/${encodeURIComponent(reportId)}/paras`, { category: value("category"), observation: value("observation"), amount_at_risk_paise: paise, references: value("references").split(",").map((ref) => ref.trim()).filter(Boolean), recommendation: value("recommendation") });
        setNotice("Audit para raised."); await qc.invalidateQueries({ queryKey: ["internal-paras"] });
      }
      form.reset();
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack" aria-labelledby="internal-audit-heading">
    <PageHeader id="internal-audit-heading" eyebrow="Zonal office" title="Internal audit" description="Create reports and raise paras for offices in your zone." current="Internal audit" />
    <ProblemMessage error={error ?? paras.error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    <form className="card stack" aria-label="Create internal audit report" onSubmit={(e) => void submit(e, "report")}>
      <h2>Create report</h2><label>Office ID<input name="office_id" required minLength={3} maxLength={40} /></label>
      <div className="form-row"><label>Period from<input name="period_from" type="date" required /></label><label>Period to<input name="period_to" type="date" required /></label></div>
      <label>Scope<textarea name="scope" required minLength={20} maxLength={4000} /></label><div className="actions"><button className="primary" disabled={busy}>Create report</button></div>
    </form>
    {reportId ? <form className="card stack" aria-label={`Add para to ${reportId}`} onSubmit={(e) => void submit(e, "para")}>
      <h2>Add para to {reportId}</h2><label>Category<select name="category">{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
      <label>Observation<textarea name="observation" required minLength={20} maxLength={4000} /></label>
      <label>Amount at risk (₹)<input name="amount_at_risk" type="number" min="0" step="0.01" required /></label>
      <label>References (comma-separated)<input name="references" /></label><label>Recommendation<textarea name="recommendation" required maxLength={4000} /></label>
      <div className="actions"><button className="primary" disabled={busy}>Raise para</button></div>
    </form> : null}
    <section className="card stack" aria-labelledby="zone-paras-heading"><h2 id="zone-paras-heading">Zone's paras</h2>
      {paras.data?.data.map((para) => <article className="card stack" key={para.para_id}><h3>{para.para_id} · {para.category}</h3>
        <p>{para.office_id} · {statusLabel(para.state, t)} {para.overdue ? <span className="state-pill">Overdue</span> : null} · Reply due {para.reply_due}</p>
        <p>{para.observation}</p><p>Amount at risk: {rupees(para.amount_at_risk_paise)}</p><p>Recommendation: {para.recommendation}</p>
      </article>)}{paras.data && !paras.data.data.length ? <p className="muted">No paras in your zone.</p> : null}
    </section>
  </section>;
}
