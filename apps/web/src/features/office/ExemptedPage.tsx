import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

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
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const officer = session.data?.stakeholder === "fo.exemption";
  const stepUp = useStepUp();
  const [content, setContent] = useState(header);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
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

  return <section className="stack" aria-labelledby="past-accumulation-heading">
    <PageHeader id="past-accumulation-heading" eyebrow="Exemption cell" title="Past accumulation ingestion"
      description="Record member balances transferred from an exempted trust. Review the total before confirming with a one-time code." current="Past accumulations" />
    <ProblemMessage error={error ?? session.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !officer ? <p className="pending-notice">This service is available to the Exemption cell.</p> : null}
    {officer ? <>
      <form className="card stack" aria-label="Ingest past accumulations" onSubmit={(e) => void ingest(e)}>
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
