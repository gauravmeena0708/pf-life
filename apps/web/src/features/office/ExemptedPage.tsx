import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError, api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";
import { RankingsTable, type Ranking } from "../exempted/RankingsPage";
import { ReturnsView, type TrustReturn, type TrustFlag } from "../exempted/ReturnsView";
import { useTranslation } from "react-i18next";
import { statusLabel } from "../statusLabel";
import { AuditsSection } from "../exempted/AuditsSection";
import { ProceedingsQueue } from "../exempted/ProceedingsPage";

interface IngestionResult {
  batch_id: string; establishment_id: string; legal_name: string; transfer_reference: string; members: number; total_paise: number;
  lines: { line: number; uan: string; account_link_id: string; employee_paise: number; employer_paise: number; pension_paise: number; journal_id: string }[];
}
const header = "uan,account_link_id,employee_rupees,employer_rupees,pension_rupees";

function accumulation(content: string): { total: number; errors: string[] } {
  let total = 0; let members = 0;
  const errors: string[] = []; const seen = new Set<string>();
  content.split(/\r?\n/).forEach((raw, index) => {
    if (!raw.trim() || raw.trim().toLowerCase() === header) return;
    const parts = raw.split(",").map((part) => part.trim());
    if (parts.length !== 5 || !/^[0-9]{12}$/.test(parts[0]) || !parts[1]
      || parts.slice(2).some((part) => !/^\d+(\.\d{1,2})?$/.test(part))) {
      errors.push(`Line ${index + 1}: enter ${header}, with non-negative rupee amounts and at most two decimal places.`); return;
    }
    if (seen.has(parts[1])) { errors.push(`Line ${index + 1}: account ${parts[1]} is repeated.`); return; }
    seen.add(parts[1]);
    const paise = parts.slice(2).reduce((sum, part) => {
      const [whole, fraction = ""] = part.split(".");
      return sum + Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
    }, 0);
    if (!Number.isSafeInteger(paise) || paise <= 0) { errors.push(`Line ${index + 1}: enter a positive total within the supported range.`); return; }
    total += paise; members++;
  });
  if (!Number.isSafeInteger(total)) errors.push("The total is outside the supported range.");
  if (!members && !errors.length) errors.push("Enter at least one member line.");
  return { total, errors };
}

export function ExemptedPage() {
  const { t } = useTranslation(); const qc = useQueryClient(); const [selected, setSelected] = useState<Ranking | null>(null);
  const selectedReturns = useQuery({ queryKey: ["office-trust-returns", selected?.establishment_id], enabled: !!selected, retry: false,
    queryFn: () => api<Envelope<{ returns: TrustReturn[] }>>(`/api/v1/office/exempted/${encodeURIComponent(selected!.establishment_id)}/returns`) });
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const officer = session.data?.stakeholder === "fo.exemption";
  const stepUp = useStepUp();
  const [content, setContent] = useState(header);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [grounds, setGrounds] = useState<string[]>([]);
  const [result, setResult] = useState<IngestionResult | null>(null);
  const preview = accumulation(content);

  async function ingest(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!officer || busy) return;
    const f = new FormData(e.currentTarget);
    const estId = String(f.get("establishment_id") ?? "").trim();
    const transfer_reference = String(f.get("transfer_reference") ?? "").trim();
    const submittedContent = content;
    const calculated = accumulation(submittedContent);
    setBusy(true); setError(null); setResult(null);
    try {
      if (calculated.errors.length) throw new ApiError({ type: "/problems/validation", status: 422, title: "Check the member lines", errors: calculated.errors });
      if (!estId || transfer_reference.length < 4) throw new Error("Enter the establishment ID and a transfer reference of at least four characters.");
      const token = await stepUp.ask({ action: "ingest-past-accumulation", resourceId: estId, amountPaise: calculated.total,
        summary: `Ingest past accumulations for ${estId}, transfer ${transfer_reference}, totalling ${rupees(calculated.total)}.` });
      if (!token) return;
      setResult((await command<Envelope<IngestionResult>>("POST", `/api/v1/office/exempted/${encodeURIComponent(estId)}/past-accumulation-ingestions`,
        { transfer_reference, content: submittedContent }, { stepUpToken: token })).data);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  async function act(event: FormEvent<HTMLFormElement>, flag: TrustFlag) {
    event.preventDefault(); if (!selected || busy) return; const f = new FormData(event.currentTarget);
    const action = String(f.get("action")); const note = String(f.get("note") || "").trim();
    if (flag.category === "A" && action === "ADVICE") return;
    setBusy(true); setError(null);
    try { const token = await stepUp.ask({ action: "action-trust-flag", resourceId: flag.flag_id, summary: `${statusLabel(action, t)} for ${flag.flag_id}: ${note}` });
      if (!token) return;
      await command("POST", `/api/v1/office/exempted/${encodeURIComponent(selected.establishment_id)}/flags/${encodeURIComponent(flag.flag_id)}/actions`, { action, note }, { stepUpToken: token });
      await qc.invalidateQueries({ queryKey: ["office-trust-returns", selected.establishment_id] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  const flagGrounds = (selectedReturns.data?.data.returns ?? []).filter((item) => item.state !== "SUPERSEDED").flatMap((item) => item.flags.filter((flag) => flag.category === "A" && !flag.action));
  const candidates = [...flagGrounds.map((flag) => ({ id: flag.flag_id, code: flag.code, label: `${statusLabel(flag.code, t)} · ${flag.flag_id}` })),
    ...["CONDITION_25", "CONDITION_29", "AUDIT_FINDINGS", "COMPLAINT"].map((code) => ({ id: code, code, label: statusLabel(code, t) }))];
  async function cancel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected || !grounds.length) { setError(new Error("Select at least one ground.")); return; }
    const f = new FormData(event.currentTarget);
    const body = { grounds: candidates.filter((item) => grounds.includes(item.id)).map((item) => ({ code: item.code, text: String(f.get(`ground-${item.id}`) || "").trim() })),
      flag_ids: flagGrounds.filter((flag) => grounds.includes(flag.flag_id)).map((flag) => flag.flag_id), note: String(f.get("note") || "").trim() };
    if (body.grounds.some((item) => !item.text)) { setError(new Error("Describe every selected ground.")); return; }
    setBusy(true); setError(null);
    try { const token = await stepUp.ask({ action: "show-cause-exemption", resourceId: selected.establishment_id, summary: `Open cancellation show-cause for ${selected.legal_name}.` });
      if (!token) return; await command("POST", `/api/v1/office/exempted/${encodeURIComponent(selected.establishment_id)}/cancellation-proceedings`, body, { stepUpToken: token });
      setGrounds([]); await qc.invalidateQueries({ queryKey: ["exemption-proceedings"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  const actions = ["DIRECTION_TO_RECTIFY", "ADVICE", "SHOW_CAUSE_NOTICE", "REFERRED_FOR_CANCELLATION", "CLOSED_RECTIFIED"];
  return <section className="stack" aria-labelledby="exempted-heading">
    <PageHeader id="exempted-heading" eyebrow="Exemption cell" title="Exempted establishments"
      description="Supervise the trusts' monthly returns, scores and flags, and record member balances brought in from an exempted trust." current="Exempted establishments" />
    <ProblemMessage error={error ?? session.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !officer ? <p className="pending-notice">This service is available to the Exemption cell.</p> : null}
    {officer ? <>
      <RankingsTable onSelect={setSelected} />
      {selected ? <section className="card stack" aria-labelledby="selected-trust-heading"><h2 id="selected-trust-heading">{selected.legal_name} · Monthly returns</h2>
        <ProblemMessage error={selectedReturns.error} />{selectedReturns.isLoading ? <p role="status">Loading returns…</p> : null}
        <ReturnsView returns={selectedReturns.data?.data.returns ?? []}>{(item) => item.flags.filter((flag) => !flag.action && item.state !== "SUPERSEDED").map((flag) => <form key={flag.flag_id} className="form-row" aria-label={`Action flag ${flag.flag_id}`} onSubmit={(e) => void act(e, flag)}>
          <label>{statusLabel(flag.code, t)} · Action<select name="action">{actions.filter((action) => flag.category !== "A" || action !== "ADVICE").map((action) => <option key={action} value={action}>{statusLabel(action, t)}</option>)}</select></label>
          <label>Note<textarea name="note" minLength={1} maxLength={2000} required /></label><button type="submit" className="primary" disabled={busy}>Record action</button></form>)}</ReturnsView>
      </section> : null}
      {selected ? <><AuditsSection estId={selected.establishment_id} />
        <form className="card stack" aria-label="Open cancellation (show-cause notice, Form CE-1)" onSubmit={(e) => void cancel(e)}>
          <h2>Open cancellation (show-cause notice, Form CE-1)</h2><fieldset className="stack"><legend>Grounds</legend>
            {candidates.map((item) => <div key={item.id} className="form-row"><label><input type="checkbox" checked={grounds.includes(item.id)} onChange={(e) => setGrounds((old) => e.target.checked ? [...old, item.id] : old.filter((id) => id !== item.id))} /> {item.label}</label>
              {grounds.includes(item.id) ? <label>Ground details · {item.label}<input name={`ground-${item.id}`} required /></label> : null}</div>)}
          </fieldset><label>Note<textarea name="note" required /></label><button className="primary" type="submit" disabled={busy || !!stepUp.request}>Issue show-cause notice</button>
        </form></> : null}
      <ProceedingsQueue />
      <form className="card stack" aria-labelledby="past-accumulation-heading" onSubmit={(e) => void ingest(e)}>
        <h2 id="past-accumulation-heading">Past accumulation ingestion</h2>
        <p className="muted small">Record member balances transferred from an exempted trust. Review the total before confirming with a one-time code.</p>
        <fieldset className="stack" disabled={busy || !!stepUp.request}><legend>Transfer and member balances</legend>
          <label>Establishment ID<input name="establishment_id" required defaultValue="EST-DEMO-0003" /></label>
          <label>Transfer reference<input name="transfer_reference" required minLength={4} maxLength={80} /></label>
          <label>{header}<textarea name="content" required minLength={10} maxLength={200000} rows={10} value={content} onChange={(e) => setContent(e.target.value)} aria-describedby="accumulation-csv-help" /></label>
          <p id="accumulation-csv-help" className="muted">One member per line; the header is optional. Enter the three balances in rupees.</p>
          <p aria-live="polite">Total to ingest: <strong>{preview.errors.length ? "Check the CSV lines" : rupees(preview.total)}</strong></p>
          <div className="actions"><button type="submit" className="primary">Ingest past accumulations</button></div>
        </fieldset>
      </form>
      {result ? <section className="card stack" aria-label="Ingestion result" role="status">
        <h2>Batch {result.batch_id}</h2><p>{result.legal_name} · {result.establishment_id} · Transfer {result.transfer_reference}</p>
        <p>{result.members} members · {rupees(result.total_paise)}</p>
        <div className="table-scroll"><table><thead><tr><th scope="col">Line</th><th scope="col">UAN</th><th scope="col">Account</th><th scope="col">Employee</th><th scope="col">Employer</th><th scope="col">Pension</th><th scope="col">Journal</th></tr></thead>
          <tbody>{result.lines.map((line) => <tr key={line.line}><th scope="row">{line.line}</th><td>{line.uan}</td><td>{line.account_link_id}</td>
            <td>{rupees(line.employee_paise)}</td><td>{rupees(line.employer_paise)}</td><td>{rupees(line.pension_paise)}</td><td>{line.journal_id}</td></tr>)}</tbody></table></div>
      </section> : null}
    </> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
