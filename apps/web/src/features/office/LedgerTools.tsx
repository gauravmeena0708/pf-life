import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();

interface Lock { lock_id: string; lock_scope: string; resource_key: string; owner_ref: string; status: string; orphaned_because: string | null;
  acquired_at: string; expires_at: string; released_at: string | null; release_reason: string | null; owner: { case_id: string; state: string } | null }

/** OIC: locks on a member's ledger; an orphaned one (owner gone or expired) is released with a recorded reason. */
export function LocksSection() {
  const stepUp = useStepUp();
  const [uan, setUan] = useState("100000000005");
  const [data, setData] = useState<{ active: Lock[]; recently_released: Lock[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = async (id = uan) => {
    setError(null);
    try { setData((await api<Envelope<{ active: Lock[]; recently_released: Lock[] }>>(`/api/v1/office/members/${id}/locks`)).data); } catch (cause) { setError(cause); }
  };
  const release = (lock: Lock) => async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const reason = text(new FormData(e.currentTarget), "reason");
    setError(null);
    try {
      const token = await stepUp.ask({ action: "release-lock", resourceId: lock.lock_id, summary: `Release lock ${lock.lock_id} held by ${lock.owner_ref}.` });
      if (!token) return;
      await command("POST", `/api/v1/office/system/locks/${lock.lock_id}/release`, { reason }, { stepUpToken: token });
      await load();
    } catch (cause) { setError(cause); }
  };
  return (
    <section className="card stack" aria-labelledby="locks-heading"><h2 id="locks-heading">Ledger locks</h2>
      <p className="muted small">A claim or transfer case locks the member's ledger while it is open. A lock whose owner is gone or has expired
        is orphaned and blocks decisions ("Unable to lock process"). Synthetic demo: UAN 100000000005 has one left by a dead batch run.</p>
      <ProblemMessage error={error} />
      <form className="search-input-row" onSubmit={(e) => { e.preventDefault(); void load(); }}>
        <label>UAN<input value={uan} onChange={(e) => setUan(e.target.value)} required pattern="[0-9]{12}" inputMode="numeric" /></label>
        <button type="submit">Show locks</button></form>
      {data ? <>
        {data.active.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Lock</th><th scope="col">Scope</th><th scope="col">Held by</th>
          <th scope="col">Expires</th><th scope="col">Status</th><th scope="col">Release</th></tr></thead>
          <tbody>{data.active.map((l) => <tr key={l.lock_id}><td><code>{l.lock_id}</code><div className="muted small">{l.resource_key}</div></td>
            <td>{l.lock_scope.replaceAll("_", " ").toLowerCase()}</td><td>{l.owner_ref}{l.owner ? ` (${l.owner.state})` : ""}</td>
            <td>{new Date(l.expires_at).toLocaleString()}</td>
            <td><span className="state-pill">{l.status}</span>{l.orphaned_because ? <div className="muted small">{l.orphaned_because}</div> : null}</td>
            <td>{l.status === "ORPHANED" ? <form className="stack" onSubmit={(e) => void release(l)(e)}>
              <label>Reason (recorded)<input name="reason" required minLength={10} /></label><button type="submit" className="primary">Release</button></form>
              : <span className="muted small">Goes with its case</span>}</td></tr>)}</tbody></table></div> : <p className="muted">No active locks.</p>}
        {data.recently_released.length ? <details><summary>Recently released ({data.recently_released.length})</summary>
          <ul className="plain-list">{data.recently_released.map((l) => <li key={l.lock_id}><code>{l.lock_id}</code> — {l.release_reason}</li>)}</ul></details> : null}
      </> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}

interface AnnexureFile { annexure_id: string; uan: string; direction: string; from_member_id: string; from_office_id: string; to_member_id: string;
  to_office_id: string; amount_paise: number; reco_status: string; reco: { checks?: Record<string, boolean> } | null }

/** DA (accounts): ANNEXURE K FILE, ANNEXURE K RECO (transfer and member records) and ANNEXURE K VDR RECO (receipt). */
export function AnnexureKSection() {
  const stepUp = useStepUp();
  const [direction, setDirection] = useState("");
  const [files, setFiles] = useState<AnnexureFile[] | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = async () => {
    setError(null);
    try { setFiles((await api<Envelope<{ files: AnnexureFile[] }>>(`/api/v1/office/annexure-k-files${direction ? `?direction=${direction}` : ""}`)).data.files); }
    catch (cause) { setError(cause); }
  };
  const reconcile = (file: AnnexureFile) => async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const f = new FormData(e.currentTarget); const amount = Math.round(Number(text(f, "amount")) * 100);
    setError(null); setResult(null);
    try {
      if (text(f, "kind") === "VDR") {
        const token = await stepUp.ask({ action: "reconcile-annexure-k-vdr", resourceId: file.annexure_id, amountPaise: amount,
          summary: `Match Annexure K ${file.annexure_id} with VDR receipt ${text(f, "receipt")} (${rupees(amount)}).` });
        if (!token) return;
        const r = await command<Envelope<{ result: string; difference_paise: number }>>("POST", `/api/v1/office/annexure-k-files/${file.annexure_id}/vdr-reconciliations`,
          { receipt_ref: text(f, "receipt"), vdr_receipt_paise: amount }, { stepUpToken: token });
        setResult(`VDR reconciliation: ${r.data.result}${r.data.difference_paise ? ` (difference ${rupees(r.data.difference_paise)})` : ""}.`);
      } else {
        const token = await stepUp.ask({ action: "reconcile-annexure-k", resourceId: file.annexure_id, summary: `Reconcile Annexure K ${file.annexure_id}.` });
        if (!token) return;
        const r = await command<Envelope<AnnexureFile>>("POST", `/api/v1/office/annexure-k-files/${file.annexure_id}/reconciliations`,
          { declared_uan: text(f, "uan"), declared_amount_paise: amount }, { stepUpToken: token });
        setResult(`Annexure K reconciliation: ${r.data.reco_status}.`);
      }
      await load();
    } catch (cause) { setError(cause); }
  };
  return (
    <section className="card stack" aria-labelledby="annexure-heading"><h2 id="annexure-heading">Annexure K files and reconciliation</h2>
      <p className="muted small">Each posted Form 13 transfer gives an Annexure K from the office of the previous member ID to the office of the new one.</p>
      <ProblemMessage error={error} />
      {result ? <p role="status" className="ok">{result}</p> : null}
      <div className="search-input-row"><label>Direction<select value={direction} onChange={(e) => setDirection(e.target.value)}>
        <option value="">All</option><option value="INWARD">Inward</option><option value="OUTWARD">Outward</option></select></label>
        <button type="button" onClick={() => void load()}>List files</button></div>
      {files ? files.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Annexure K</th><th scope="col">From → to</th><th scope="col">Amount</th>
        <th scope="col">Status</th><th scope="col">Reconcile</th></tr></thead>
        <tbody>{files.map((a) => <tr key={a.annexure_id}><td><code>{a.annexure_id}</code><div className="muted small">UAN {a.uan} · {a.direction.replace("_", " ").toLowerCase()}</div></td>
          <td>{a.from_member_id} ({a.from_office_id}) → {a.to_member_id} ({a.to_office_id})</td><td>{rupees(a.amount_paise)}</td>
          <td><span className="state-pill">{a.reco_status}</span>{a.reco?.checks ? <div className="muted small">{Object.entries(a.reco.checks).filter(([, ok]) => !ok).map(([k]) => k.replaceAll("_", " ")).join(", ")}</div> : null}</td>
          <td><form className="stack" onSubmit={(e) => void reconcile(a)(e)}>
            <label>Against<select name="kind"><option value="RECORDS">Transfer and member records</option><option value="VDR">VDR receipt</option></select></label>
            <label>UAN on the Annexure K<input name="uan" defaultValue={a.uan} pattern="[0-9]{12}" /></label>
            <label>Amount (₹)<input name="amount" required type="number" min={0} step="0.01" /></label>
            <label>VDR receipt ref.<input name="receipt" placeholder="VDR/2026/…" /></label>
            <button type="submit">Reconcile</button></form></td></tr>)}</tbody></table></div> : <p className="muted">No Annexure K files.</p> : null}
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
