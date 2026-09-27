import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, command, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import type { RuleSet, RuleSetSummary } from "./types";

const STATUS: Record<string, string> = {
  IN_FORCE: "In force", SCHEDULED: "Scheduled", DRAFT: "Draft", SUBMITTED: "Awaiting approval", SUPERSEDED: "Superseded",
};

function nextMonth(): string {
  const d = new Date();
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1)).toISOString().slice(0, 10);
}

/** Policy administration: every rule-set version, and a new draft copied from the one in force. */
export function PolicyListPage() {
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const list = useQuery({ queryKey: ["rule-sets"], retry: false,
    queryFn: () => api<Envelope<{ today: string; items: RuleSetSummary[] }>>("/api/v1/ho/config/rule-sets") });
  const items = list.data?.data.items ?? [];
  const inForce = items.find((i) => i.status === "IN_FORCE");
  const drafter = session.data?.stakeholder === "ho.acc_hq";

  async function createDraft(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!inForce) return;
    const f = new FormData(e.currentTarget);
    setError(null);
    try {
      const base = await api<Envelope<RuleSet>>(`/api/v1/ho/config/rule-sets/${inForce.version_id}`);
      const created = await command<Envelope<RuleSet>>("POST", "/api/v1/ho/config/rule-sets", {
        base_version_id: inForce.version_id, rule_version: String(f.get("rule_version")).trim(),
        effective_from: String(f.get("effective_from")), change_note: String(f.get("change_note")).trim(),
        document: base.data.document,
      });
      navigate(`/policy/${created.data.version_id}`);
    } catch (cause) { setError(cause); }
  }

  return (
    <section className="stack" aria-labelledby="policy-heading">
      <PageHeader id="policy-heading" eyebrow="Head office · policy administration" title="Rules and limits"
        description="Wage ceilings, contribution rates, claim types, who approves which claim, what is settled automatically, and grievance service levels. Changes take effect from a date, after maker-checker approval — no code change."
        current="Policy administration" />
      <ProblemMessage error={list.error} />
      <ProblemMessage error={error} />
      <section className="card stack" aria-labelledby="versions-heading">
        <h2 id="versions-heading">Versions</h2>
        <div className="table-scroll"><table>
          <thead><tr><th scope="col">Version</th><th scope="col">Status</th><th scope="col">Effective from</th><th scope="col">Change</th></tr></thead>
          <tbody>{items.map((i) => (
            <tr key={i.version_id}>
              <td><Link to={`/policy/${i.version_id}`}><code>{i.rule_version}</code></Link></td>
              <td><span className="state-pill">{STATUS[i.status] ?? i.status}</span></td>
              <td>{i.effective_from}</td>
              <td>{i.change_note}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </section>
      {drafter && inForce ? (
        <form className="card stack" onSubmit={(e) => void createDraft(e)} aria-labelledby="new-heading">
          <h2 id="new-heading">Start a change</h2>
          <p className="muted">Copies the rules in force ({inForce.rule_version}). You then edit the copy, check the effect, and submit it to the CPFC.</p>
          <div className="form-row">
            <label>Version name<input name="rule_version" required pattern="[a-z0-9][a-z0-9.\-]{2,58}" defaultValue={`demo-rules-${new Date().getFullYear()}.${items.length + 1}`} /></label>
            <label>Takes effect from<input name="effective_from" type="date" required defaultValue={nextMonth()} min={list.data?.data.today} /></label>
          </div>
          <label>What is changing and why (cite the notification)<textarea name="change_note" required minLength={10} maxLength={2000} /></label>
          <div className="actions"><button type="submit" className="primary">Create draft</button></div>
        </form>
      ) : null}
    </section>
  );
}
