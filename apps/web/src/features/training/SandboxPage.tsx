import { useState, type FormEvent } from "react";

import { command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import "./SandboxPage.css";

interface Sandbox { sandbox_id: string; expires_on: string; training_logins: { username: string; persona: string }[]; note: string }
const personas = ["member-a", "member-b", "emp-owner", "emp-preparer", "emp-signatory", "do-caseworker", "ro-ss", "ro-ao", "ro-apfc", "ro-cashier"];

export function SandboxPage() {
  const [error, setError] = useState<unknown>(null); const [sandbox, setSandbox] = useState<Sandbox | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return;
    const f = new FormData(e.currentTarget); setError(null); setBusy(true); setSandbox(null);
    try { setSandbox((await command<Envelope<Sandbox>>("POST", "/api/v1/training/sandboxes", {
      course: String(f.get("course")).trim(), trainees: Number(f.get("trainees")), personas: f.getAll("personas").map(String), starts_on: String(f.get("starts_on")),
    })).data); } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack" aria-labelledby="training-heading">
    <PageHeader id="training-heading" eyebrow="Training" title="Training sandbox" current="Training sandbox" description="Prepare synthetic login records for a course." />
    <p className="pending-notice">Synthetic data only; training logins are records, not real accounts.</p><ProblemMessage error={error} />
    <form className="card stack" onSubmit={(e) => void submit(e)}><h2>Create sandbox</h2><fieldset className="stack" disabled={busy}><legend>Course details</legend>
      <div className="form-row"><label>Course<input name="course" required minLength={5} maxLength={200} /></label>
        <label>Trainees<input name="trainees" type="number" required min={1} max={60} defaultValue={1} /></label>
        <label>Starts on<input name="starts_on" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} /></label></div>
      <fieldset><legend>Personas</legend><div className="training-personas">{personas.map((persona) => <label key={persona}><input type="checkbox" name="personas" value={persona} /> {persona}</label>)}</div></fieldset>
      <div className="actions"><button type="submit" className="primary">Create sandbox</button></div></fieldset></form>
    {sandbox ? <section className="card stack" aria-labelledby="sandbox-result-heading"><h2 id="sandbox-result-heading">Sandbox {sandbox.sandbox_id}</h2>
      <p>Expires on {sandbox.expires_on}</p><p className="muted">{sandbox.note}</p>
      <div className="table-scroll"><table><thead><tr><th scope="col">Training login</th><th scope="col">Persona</th></tr></thead>
        <tbody>{sandbox.training_logins.map((login) => <tr key={login.username}><th scope="row">{login.username}</th><td>{login.persona}</td></tr>)}</tbody></table></div></section> : null}
  </section>;
}
