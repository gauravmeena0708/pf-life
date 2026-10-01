import { useTranslation } from "react-i18next";
import { useState, type FormEvent } from "react";

import { command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";

interface CampResult { reference: string; next_step: string; camp: { camp_id: string; venue: string; request_counts: Record<string, number> } }
const kinds = ["GRIEVANCE", "CLAIM_HELP", "KYC_UPDATE", "INOPERATIVE_ACCOUNT", "PENSION", "UAN_HELP"];

export function CampPage() {
  const { t } = useTranslation(); const [error, setError] = useState<unknown>(null); const [result, setResult] = useState<CampResult | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return;
    const f = new FormData(e.currentTarget); const value = (key: string) => String(f.get(key) ?? "").trim();
    setError(null); setResult(null); setBusy(true);
    try { setResult((await command<Envelope<CampResult>>("POST", `/api/v1/office/outreach-camps/${encodeURIComponent(value("camp_id"))}/assisted-requests`, {
      kind: value("kind"), name: value("name"), mobile: value("mobile"), uan: value("uan") || null, details: value("details"),
    })).data); } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack" aria-labelledby="camp-heading"><PageHeader id="camp-heading" eyebrow="Field office" title="Nidhi Aapke Nikat camp" current="Camp requests"
    description="Record assistance provided at an outreach camp." /><ProblemMessage error={error} />
    <form className="card stack" onSubmit={(e) => void submit(e)}><h2>Assisted request</h2><fieldset className="stack" disabled={busy}><legend>Camp and visitor</legend>
      <div className="form-row"><label>Camp ID<input name="camp_id" required defaultValue="NAN-RO1-2026-10" /></label>
        <label>Request kind<select name="kind">{kinds.map((kind) => <option key={kind} value={kind}>{statusLabel(kind, t)}</option>)}</select></label></div>
      <div className="form-row"><label>Name<input name="name" required maxLength={200} /></label><label>Mobile<input name="mobile" required pattern="[0-9]{10}" inputMode="numeric" /></label>
        <label>UAN (optional)<input name="uan" pattern="[0-9]{12}" inputMode="numeric" /></label></div>
      <label>Details<textarea name="details" required minLength={10} maxLength={4000} /></label><div className="actions"><button type="submit" className="primary">Record request</button></div>
    </fieldset></form>
    {result ? <section className="card stack" aria-labelledby="camp-result-heading"><h2 id="camp-result-heading">Reference {result.reference}</h2>
      <p><strong>Next step:</strong> {result.next_step}</p><h3>Camp summary · {result.camp.camp_id}</h3><p className="muted">{result.camp.venue}</p>
      <ul>{Object.entries(result.camp.request_counts).map(([kind, count]) => <li key={kind}>{statusLabel(kind, t)}: {count}</li>)}</ul></section> : null}
  </section>;
}
