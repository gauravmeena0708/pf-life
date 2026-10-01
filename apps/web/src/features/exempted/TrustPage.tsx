import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import "./TrustPage.css";
import { MonthlyReturn } from "./MonthlyReturn";

interface Profile { establishment: { establishment_id: string; legal_name: string }; kind: string; kind_description: string; pf_exempt: boolean; pension_exempt: boolean; edli_exempt: boolean; notification_no: string; notification_date: string; effective_from: string; status: string; trust_name: string; conditions: { number: number; description: string }[]; note: string }
interface Request { annexure_id: string; transfer_id: string; from_account_link_id: string; to_account_link_id: string; state: string; employee_paise: number | null; employer_paise: number | null }
const paise = (value: FormDataEntryValue | null) => Math.round(Number(value) * 100);

export function TrustPage() {
  const { t } = useTranslation(); const qc = useQueryClient();
  const keys = useRef<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const profile = useQuery({ queryKey: ["trust-profile"], retry: false, queryFn: () => api<Envelope<Profile>>("/api/v1/exempted/me/profile") });
  const requests = useQuery({ queryKey: ["trust-annexure-requests"], retry: false,
    queryFn: () => api<Envelope<{ requests: Request[] }>>("/api/v1/exempted/me/annexure-k-requests") });
  const submit = (event: FormEvent<HTMLFormElement>, id: string) => { event.preventDefault(); const f = new FormData(event.currentTarget);
    if (String(f.get("service_to")) < String(f.get("service_from"))) { setError(new Error("Service end must be on or after the start.")); return; }
    const body = { annexure_id: id, employee_paise: paise(f.get("employee")), employer_paise: paise(f.get("employer")),
      service_from: String(f.get("service_from")), service_to: String(f.get("service_to")), breaks_months: Number(f.get("breaks")), interest_note: String(f.get("interest_note")).trim() || null };
    setError(null); setNotice(null); setBusy(true);
    void (async () => { try { const key = keys.current[id] ??= newIdempotencyKey();
      await command("POST", "/api/v1/exempted/me/annexure-k-submissions", body, { idempotencyKey: key });
      delete keys.current[id]; setNotice(`Annexure K ${id} submitted.`); await qc.invalidateQueries({ queryKey: ["trust-annexure-requests"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); } })();
  };
  const p = profile.data?.data;
  return <section className="stack" aria-labelledby="trust-page-heading">
    <PageHeader id="trust-page-heading" eyebrow="Exempted establishment" title="Trust" current="Trust" description="PF trust profile and Annexure K requests." />
    <ProblemMessage error={profile.error} /><ProblemMessage error={requests.error} /><ProblemMessage error={error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}
    {p ? <section className="card stack trust-profile" aria-labelledby="trust-profile-heading"><h2 id="trust-profile-heading">{p.trust_name}</h2>
      <p>{p.establishment.legal_name} · {p.establishment.establishment_id} · <span className="state-pill">{statusLabel(p.status, t)}</span></p>
      <dl className="kv"><dt>Exemption kind</dt><dd>{p.kind} · {p.kind_description}</dd><dt>PF</dt><dd>{p.pf_exempt ? "Exempted" : "With EPFO"}</dd>
        <dt>Pension (EPS)</dt><dd>{p.pension_exempt ? "Exempted" : "With EPFO"}</dd><dt>EDLI</dt><dd>{p.edli_exempt ? "Exempted" : "With EPFO"}</dd>
        <dt>Notification</dt><dd>{p.notification_no} · {p.notification_date}</dd><dt>Effective from</dt><dd>{p.effective_from}</dd></dl>
      <p className="muted small">{p.note}</p><h3>Conditions undertaken</h3>
      <ol>{p.conditions.map((condition) => <li key={condition.number}>Condition {condition.number}: {condition.description}</li>)}</ol>
    </section> : null}
    <MonthlyReturn />
    <section className="card stack" aria-labelledby="trust-requests-heading"><h2 id="trust-requests-heading">Annexure K requests</h2>
      {requests.isLoading ? <p role="status">Loading requests…</p> : null}
      {requests.data?.data.requests.length === 0 ? <p className="muted">No Annexure K requests.</p> : null}
      {requests.data?.data.requests.map((item) => <section key={item.annexure_id} className="profile-card stack" aria-label={`Annexure K ${item.annexure_id}`}>
        <h3>{item.annexure_id} <span className="state-pill">{statusLabel(item.state, t)}</span></h3>
        <p>Transfer {item.transfer_id} · {item.from_account_link_id} → {item.to_account_link_id}</p>
        {item.state === "REQUESTED" ? <form className="stack" aria-label={`Submit Annexure K ${item.annexure_id}`} onSubmit={(event) => submit(event, item.annexure_id)}>
          <div className="form-row"><label>Employee PF (₹)<input name="employee" type="number" min="0" step="0.01" required /></label>
            <label>Employer PF (₹)<input name="employer" type="number" min="0" step="0.01" required /></label>
            <label>Service from<input name="service_from" type="date" required /></label><label>Service to<input name="service_to" type="date" required /></label>
            <label>Breaks (months)<input name="breaks" type="number" min="0" step="1" defaultValue="0" required /></label></div>
          <label>Interest note<textarea name="interest_note" maxLength={1000} /></label>
          <div className="actions"><button className="primary" type="submit" disabled={busy}>Submit Annexure K</button></div></form>
          : <p>Employee {rupees(item.employee_paise)} · Employer {rupees(item.employer_paise)}</p>}
      </section>)}
    </section>
  </section>;
}
