import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const categories = ["UNAUTHORISED_ACCESS", "DATA_BREACH", "MALWARE", "DENIAL_OF_SERVICE", "PHISHING", "IDENTITY_THEFT", "OTHER"] as const;
const severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
interface Incident {
  incident_id: string; title: string; category: string; severity: string; detected_at: string; description: string;
  affected_systems: string[]; related_event_ids: string[]; recorded_at: string; note?: string;
  cert_in: { required: boolean; due_by: string; reported_at: string | null; late: boolean; acknowledgement: string | null };
}
function IncidentDetails({ incident }: { incident: Incident }) {
  return <article className="card stack"><h3>{incident.title} · {incident.incident_id}</h3>
    <p>{incident.category} · {incident.severity} · Detected {incident.detected_at}</p><p>{incident.description}</p>
    <p>Affected systems: {incident.affected_systems.join(", ") || "None recorded"}</p>
    <p>Related events: {incident.related_event_ids.join(", ") || "None recorded"} · Recorded {incident.recorded_at}</p>
    <dl className="kv"><dt>CERT-In reporting required</dt><dd>{incident.cert_in.required ? "Yes" : "No"}</dd>
      <dt>Due by</dt><dd>{incident.cert_in.due_by}</dd><dt>Reported at</dt><dd>{incident.cert_in.reported_at ?? "Not reported"}</dd>
      <dt>Late</dt><dd>{incident.cert_in.late ? "Yes" : "No"}</dd><dt>Acknowledgement</dt><dd>{incident.cert_in.acknowledgement ?? "—"}</dd></dl>
    {incident.note ? <p>{incident.note}</p> : null}
  </article>;
}
export function SecurityIncidents() {
  const qc = useQueryClient(); const stepUp = useStepUp();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<Incident | null>(null);
  const incidents = useQuery({ queryKey: ["security-incidents"], retry: false,
    queryFn: () => api<Envelope<Incident[]>>("/api/v1/security/incidents") });
  async function record(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return;
    const form = e.currentTarget; const f = new FormData(form);
    const text = (name: string) => String(f.get(name) ?? "").trim();
    const list = (name: string) => text(name).split(",").map((part) => part.trim()).filter(Boolean);
    setBusy(true); setError(null); setResult(null);
    try {
      const category = text("category"); const severity = text("severity"); const detected = new Date(text("detected_at"));
      if (!categories.some((value) => value === category) || !severities.some((value) => value === severity)) throw new Error("Choose an incident category and severity.");
      if (!text("title") || text("description").length < 20 || Number.isNaN(detected.getTime())) throw new Error("Enter a title, detection time and description of at least 20 characters.");
      const body = { title: text("title"), category, severity, detected_at: detected.toISOString(), description: text("description"),
        affected_systems: list("affected_systems"), related_event_ids: list("related_event_ids") };
      const token = await stepUp.ask({ action: "record-security-incident", resourceId: `${category}:${severity}`,
        summary: `Record ${severity} incident ${body.title}, category ${category}, detected ${body.detected_at}.` });
      if (!token) return;
      setResult((await command<Envelope<Incident>>("POST", "/api/v1/security/incidents", body, { stepUpToken: token })).data);
      form.reset(); await qc.invalidateQueries({ queryKey: ["security-incidents"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="incidents-heading"><h2 id="incidents-heading">Security incidents</h2>
    <ProblemMessage error={error ?? incidents.error} />
    <form className="stack" aria-label="Record a security incident" onSubmit={(e) => void record(e)}>
      <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>Incident details</legend>
        <label>Title<input name="title" required maxLength={200} /></label>
        <label>Category<select name="category" required>{categories.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>
        <label>Severity<select name="severity" required>{severities.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Detected at (local time)<input name="detected_at" type="datetime-local" required /></label>
        <label>Description<textarea name="description" required minLength={20} maxLength={4000} /></label>
        <label>Affected systems (comma separated)<input name="affected_systems" /></label>
        <label>Related event IDs (comma separated)<input name="related_event_ids" /></label>
        <div className="actions"><button type="submit" className="primary">Record incident</button></div>
      </fieldset>
    </form>
    {result ? <section aria-label="Recorded incident" role="status"><IncidentDetails incident={result} /></section> : null}
    <h3>Incident register</h3>
    {incidents.isLoading ? <p role="status">Loading incidents…</p> : null}
    {incidents.data?.data.map((incident) => <IncidentDetails key={incident.incident_id} incident={incident} />)}
    {incidents.data && !incidents.data.data.length ? <p className="muted">No incidents recorded.</p> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
