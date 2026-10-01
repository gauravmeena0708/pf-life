import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useState, type FormEvent } from "react";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import "./DrPage.css";

interface Replica { database: string; lag_seconds: number; status: string; last_applied_at: string }
interface Replication { databases: Replica[]; overall_status: string; rpo_minutes: number; simulated: boolean; note: string }
interface Drill { drill_id: string; scenario: string; steps: { step: string; duration_minutes: number }[];
  rto_minutes: number; target_minutes: number; within_target: boolean; simulated: boolean; note: string }
const scenarios = ["FULL_SITE", "DATABASE", "APPLICATION_TIER"];

export function DrPage() {
  const { t } = useTranslation(); const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null); const [drill, setDrill] = useState<Drill | null>(null); const [busy, setBusy] = useState(false);
  const replication = useQuery({ queryKey: ["dr-replication"], retry: false,
    queryFn: () => api<Envelope<Replication>>("/api/v1/ndc/dr/replication-status") });
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy) return;
    const f = new FormData(e.currentTarget); const scenario = String(f.get("scenario")); const notes = String(f.get("notes") ?? "").trim();
    setError(null); setBusy(true); setDrill(null);
    try {
      const token = await stepUp.ask({ action: "run-failover-drill", resourceId: scenario,
        summary: `Record a simulated ${statusLabel(scenario, t)} failover drill.` });
      if (!token) return;
      setDrill((await command<Envelope<Drill>>("POST", "/api/v1/ndc/dr/failover-drills", { scenario, notes: notes || null }, { stepUpToken: token })).data);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="stack" aria-labelledby="dr-heading">
    <PageHeader id="dr-heading" eyebrow="ADC" title="Disaster recovery" current="Disaster recovery" description="Illustrative replication status and failover drills." />
    <p className="pending-notice">Simulated — nothing is failed over. No live replication or failover is performed.</p>
    <ProblemMessage error={error ?? replication.error} />
    <section className="card stack" aria-labelledby="replication-heading"><h2 id="replication-heading">Replication status</h2>
      {replication.isLoading ? <p role="status">Loading replication status…</p> : null}
      {replication.data ? <><p>Overall: <span className={`state-pill ${replication.data.data.overall_status === "LAGGING" ? "dr-lagging" : ""}`}>
        {statusLabel(replication.data.data.overall_status, t)}</span> · RPO: {replication.data.data.rpo_minutes} minutes</p>
        <div className="table-scroll"><table><thead><tr><th scope="col">Database</th><th scope="col">Lag</th><th scope="col">Status</th><th scope="col">Last applied</th></tr></thead>
          <tbody>{replication.data.data.databases.map((row) => <tr key={row.database}><th scope="row">{row.database}</th><td>{row.lag_seconds} seconds</td>
            <td><span className={`state-pill ${row.status === "LAGGING" ? "dr-lagging" : ""}`}>{statusLabel(row.status, t)}</span></td>
            <td>{new Date(row.last_applied_at).toLocaleString()}</td></tr>)}</tbody></table></div></> : null}
    </section>
    <section className="card stack" aria-labelledby="drill-heading"><h2 id="drill-heading">Failover drill</h2>
      <form className="stack" onSubmit={(e) => void submit(e)}><fieldset className="stack" disabled={busy}><legend>Simulation</legend>
        <label>Scenario<select name="scenario">{scenarios.map((code) => <option key={code} value={code}>{statusLabel(code, t)}</option>)}</select></label>
        <label>Notes<textarea name="notes" maxLength={2000} /></label><div className="actions"><button type="submit" className="primary">Run simulated drill</button></div>
      </fieldset></form>
      {drill ? <div role="status" className="stack"><h3>Drill {drill.drill_id}</h3><p>{statusLabel(drill.scenario, t)} · RTO {drill.rto_minutes} minutes · Target {drill.target_minutes} minutes · {drill.within_target ? "Within target" : "Outside target"}</p>
        <ol>{drill.steps.map((step) => <li key={step.step}>{step.step} — {step.duration_minutes} minutes</li>)}</ol><p className="muted">{drill.note}</p></div> : null}
    </section>
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
