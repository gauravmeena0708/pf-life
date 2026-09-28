import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

type RevisionState = "PROPOSED" | "APPROVED" | "REJECTED";
type Decision = "APPROVE" | "REJECT";

interface PensionRevision {
  revision_id: string;
  ppo_id: string;
  name: string;
  uan_masked: string;
  state: RevisionState;
  effective_from: string;
  from_rule_version: string;
  to_rule_version: string;
  old_monthly_paise: number;
  new_monthly_paise: number;
  working: string;
  arrears_paise: number;
}

const TABS: { state: RevisionState; label: string }[] = [
  { state: "PROPOSED", label: "Proposed" },
  { state: "APPROVED", label: "Approved" },
  { state: "REJECTED", label: "Rejected" },
];

export function PensionRevisionsPage() {
  const [state, setState] = useState<RevisionState>("PROPOSED");
  const [busyRevision, setBusyRevision] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const revisions = useQuery({
    queryKey: ["pension-revisions", state],
    queryFn: () => api<Envelope<{ items: PensionRevision[] }>>(`/api/v1/office/pensions/revisions?state=${state}`),
    retry: false,
  });

  async function decide(row: PensionRevision, decision: Decision, note: string) {
    setError(null);
    setNotice(null);
    if (note.length < 5) {
      setError(new Error("The decision note must contain at least five characters."));
      return;
    }
    setBusyRevision(row.revision_id);
    try {
      const token = await stepUp.ask({
        action: "approve-pension-revision",
        resourceId: row.revision_id,
        amountPaise: row.arrears_paise,
        summary: `Revise the pension of ${row.name} (${row.ppo_id}) from ${rupees(row.old_monthly_paise)} to ${rupees(row.new_monthly_paise)} a month from ${row.effective_from}, with arrears of ${rupees(row.arrears_paise)}.`,
      });
      if (!token) return;
      await command("POST", `/api/v1/office/pensions/${row.ppo_id}/revisions`,
        { revision_id: row.revision_id, decision, note }, { stepUpToken: token });
      setNotice(`${decision === "APPROVE" ? "Approved" : "Rejected"} the revision for ${row.name} (${row.ppo_id}).`);
      await qc.invalidateQueries({ queryKey: ["pension-revisions"] });
    } catch (cause) {
      setError(cause);
    } finally {
      setBusyRevision(null);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>, row: PensionRevision) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void decide(row, form.get("decision") as Decision, String(form.get("note") ?? "").trim());
  }

  return (
    <section className="stack" aria-labelledby="pension-revisions-heading">
      <PageHeader id="pension-revisions-heading" eyebrow="Pension administration" title="Pension revisions"
        description="Review changes to pensions in payment" current="Pension revisions" />
      <p className="muted small">When a published rule set changes the pension formula and says it applies to pensions in payment, each pension it would increase is proposed here. Pensions in payment are never reduced. Approving pays the arrears for the months already paid and the new amount from next month.</p>
      <div className="actions" aria-label="Revision status">
        {TABS.map((tab) => <button key={tab.state} type="button" aria-pressed={state === tab.state}
          onClick={() => { setState(tab.state); setNotice(null); setError(null); }}>{tab.label}</button>)}
      </div>
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      <ProblemMessage error={error} />
      <ProblemMessage error={revisions.error} />
      {revisions.isLoading ? <p role="status">Loading revisions…</p> : null}
      <section className="card stack" aria-labelledby="revision-list-heading">
        <h2 id="revision-list-heading">{TABS.find((tab) => tab.state === state)?.label} revisions</h2>
        {revisions.data?.data.items.length === 0 ? <p className="muted small">No {state.toLowerCase()} revisions.</p> : null}
        {revisions.data?.data.items.length ? <div className="table-scroll"><table>
          <thead><tr>
            <th scope="col">Pensioner</th><th scope="col">Effective from</th>
            <th scope="col">Monthly pension</th><th scope="col">Arrears</th>
            <th scope="col">Rules</th><th scope="col">Working</th>
            {state === "PROPOSED" ? <th scope="col">Decision</th> : null}
          </tr></thead>
          <tbody>{revisions.data.data.items.map((row) => <tr key={row.revision_id}>
            <td><strong>{row.name}</strong><br />PPO {row.ppo_id}<br /><span className="muted small">UAN {row.uan_masked}</span></td>
            <td>{row.effective_from}</td>
            <td>{rupees(row.old_monthly_paise)} → {rupees(row.new_monthly_paise)}</td>
            <td>{rupees(row.arrears_paise)}</td>
            <td>{row.from_rule_version} → {row.to_rule_version}</td>
            <td>{row.working}</td>
            {state === "PROPOSED" ? <td><form className="stack" onSubmit={(event) => submit(event, row)}>
              <fieldset className="case-options"><legend>Decision for {row.ppo_id}</legend>
                <label className="check-row"><input type="radio" name="decision" value="APPROVE" required />Approve</label>
                <label className="check-row"><input type="radio" name="decision" value="REJECT" />Reject</label>
              </fieldset>
              <label>Decision note<textarea name="note" required minLength={5} maxLength={1000} /></label>
              <div className="actions"><button type="submit" className="primary" disabled={busyRevision !== null}>Record decision</button></div>
            </form></td> : null}
          </tr>)}</tbody>
        </table></div> : null}
      </section>
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
