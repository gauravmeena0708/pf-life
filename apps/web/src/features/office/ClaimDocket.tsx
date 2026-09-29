import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

interface Docket { cad_id: string; generated_by_role: string | null; gross_paise: number; interest_paise: number; tds_paise: number;
  net_paise: number; tax_basis: string; rule_version: string; created_at: string | null; versions?: Docket[] }

/** Claim Approval Docket (CITES manuals): each officer generates it again before recommending or deciding. */
export function ClaimDocket({ claimId, ready, canGenerate, onGenerated }: { claimId: string; ready: boolean; canGenerate: boolean; onGenerated: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const docket = useQuery({ queryKey: ["claim-docket", claimId], retry: false,
    queryFn: () => api<Envelope<Docket>>(`/api/v1/office/claims/${claimId}/cad`) });
  const generate = async () => {
    setBusy(true); setError(null);
    try {
      await command("POST", `/api/v1/office/claims/${claimId}/cad`);
      await docket.refetch();
      window.setTimeout(onGenerated, 1500);                // the work queue sees the docket a moment later (event)
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  };
  const d = docket.data?.data;
  return (
    <section className="card stack" aria-labelledby="docket-heading"><h2 id="docket-heading">Claim Approval Docket (CAD)</h2>
      <ProblemMessage error={error} />
      {canGenerate ? <p className={ready ? "ok" : "pending-notice"}>{ready ? "Your docket for this step is generated. You can act on the claim."
        : "Generate the Claim Approval Docket before you recommend or decide (CITES: mandatory at every level)."}</p> : null}
      {canGenerate ? <div className="actions"><button type="button" className={ready ? "" : "primary"} disabled={busy} onClick={() => void generate()}>
        {ready ? "Regenerate docket" : "Generate docket"}</button></div> : null}
      {d ? <>
        <dl className="kv"><dt>Docket</dt><dd><code>{d.cad_id}</code> by {d.generated_by_role ?? "—"}</dd><dt>Gross</dt><dd>{rupees(d.gross_paise)}</dd>
          <dt>Of which interest</dt><dd>{rupees(d.interest_paise)}</dd><dt>TDS</dt><dd>{rupees(d.tds_paise)} <span className="muted small">{d.tax_basis}</span></dd>
          <dt>Net payable</dt><dd><strong>{rupees(d.net_paise)}</strong></dd><dt>Rules</dt><dd>{d.rule_version} <span className="state-pill">illustrative</span></dd></dl>
        {d.versions && d.versions.length > 1 ? <details><summary>All levels ({d.versions.length})</summary>
          <ul className="plain-list">{d.versions.map((v) => <li key={v.cad_id}><code>{v.cad_id}</code> — {v.generated_by_role}, net {rupees(v.net_paise)}</li>)}</ul></details> : null}
      </> : <p className="muted">No docket yet.</p>}
    </section>
  );
}
