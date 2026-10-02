import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const url = "/api/v1/employers/me/eec-declarations";
type Totals = Record<"AC01_EPF_EE" | "AC01_EPF_ER" | "AC10_EPS" | "AC21_EDLI" | "AC02_ADMIN" | "INTEREST_7Q" | "DAMAGES_14B" | "TOTAL", number>;
interface Dues { from_month: string; to_month: string; months: unknown[]; totals_paise: Totals; employee_share_waived: boolean; trrn?: string; name?: string }
interface EecData {
  scheme: { scheme: string; open_from: string; open_until: string; joined_from: string; joined_until: string; damages_paise: number };
  open: boolean;
  candidates: { uan: string; name: string; date_of_joining: string }[];
  declarations: { declaration_id: string; uan: string; from_month: string; to_month: string; totals_paise: Totals; trrn: string; state: string }[];
}
const LABELS: [keyof Totals, string][] = [["AC01_EPF_EE", "Employee's share"], ["AC01_EPF_ER", "Employer's share to EPF"], ["AC10_EPS", "Pension (EPS)"],
  ["AC21_EDLI", "EDLI"], ["AC02_ADMIN", "Administrative charges"], ["INTEREST_7Q", "Interest (7Q)"], ["DAMAGES_14B", "Damages (lump sum)"], ["TOTAL", "Total"]];

/** EEC, 2026: enrol employees left out of EPF (April 2009 – March 2026) — declare, see the past dues, pay one challan. */
export function EecSection({ signatory }: { signatory: boolean }) {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const data = useQuery({ queryKey: ["employer-eec"], retry: false, queryFn: () => api<Envelope<EecData>>(url) });
  const [dues, setDues] = useState<Dues | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function body(form: HTMLFormElement) {
    const f = new FormData(form);
    return { uan: String(f.get("uan")), monthly_wages_paise: Math.round(Number(f.get("wages")) * 100),
      employee_share_deducted: f.get("deducted") === "on", declaration: f.get("declaration") === "on" };
  }
  async function preview(form: HTMLFormElement) {
    setBusy(true); setError(null);
    try {
      const b = body(form);
      const q = new URLSearchParams({ uan: b.uan, monthly_wages_paise: String(b.monthly_wages_paise), employee_share_deducted: String(b.employee_share_deducted) });
      setDues((await api<Envelope<Dues>>(`${url}/dues?${q.toString()}`)).data);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  async function declare(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget;
    if (!dues) { await preview(form); return; }
    setBusy(true); setError(null);
    try {
      const b = body(form);
      const token = await stepUp.ask({ action: "declare-eec", resourceId: b.uan, amountPaise: dues.totals_paise.TOTAL,
        summary: `Declare ${b.uan} under EEC, 2026: ${rupees(dues.totals_paise.TOTAL)}` });
      if (!token) return;                                          // cancelled
      setDues((await command<Envelope<Dues>>("POST", url, b, { stepUpToken: token })).data);
      await qc.invalidateQueries({ queryKey: ["employer-eec"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  const d = data.data?.data;
  return <section className="card stack" aria-labelledby="eec-heading"><h2 id="eec-heading">EEC, 2026 — enrolling employees left out</h2>
    {d ? <p>{d.scheme.scheme}, open {d.scheme.open_from} to {d.scheme.open_until}{d.open ? "" : " (closed)"}: employees who joined between
      {" "}{d.scheme.joined_from} and {d.scheme.joined_until} and were left out of EPF, still working here. Where the employee&apos;s share was
      not deducted it is waived; you pay your share, interest and administrative charges for the past months and {rupees(d.scheme.damages_paise)} damages.
      Register the employee first (face-authenticated UAN, Members › Register).</p> : null}
    <ProblemMessage error={error ?? data.error} />
    {d?.declarations.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Declaration</th><th scope="col">UAN</th>
      <th scope="col">Period</th><th scope="col">Total</th><th scope="col">Challan</th><th scope="col">State</th></tr></thead>
      <tbody>{d.declarations.map((x) => <tr key={x.declaration_id}><th scope="row">{x.declaration_id}</th><td>{x.uan}</td>
        <td>{x.from_month} – {x.to_month}</td><td>{rupees(x.totals_paise.TOTAL)}</td><td>{x.trrn}</td><td>{x.state === "PAID" ? "Paid — credited" : "Due"}</td></tr>)}</tbody>
    </table></div> : null}
    {signatory && d?.open ? (d.candidates.length ? <form className="stack" aria-label="EEC declaration" onSubmit={(e) => void declare(e)} onChange={() => setDues(null)}>
      <div className="form-row">
        <label>Employee<select name="uan" required>{d.candidates.map((c) => <option key={c.uan} value={c.uan}>{c.name} · {c.uan} · joined {c.date_of_joining}</option>)}</select></label>
        <label>Monthly wages (₹)<input name="wages" type="number" min="1" step="1" required /></label>
      </div>
      <label className="check-row"><input name="deducted" type="checkbox" /> The employee&apos;s share was deducted from the wages (then it is payable)</label>
      <label className="check-row"><input name="declaration" type="checkbox" required /> I declare the employee was left out of EPF, is alive and still works here</label>
      {dues ? <div className="stack"><h3>Dues {dues.from_month} – {dues.to_month} ({dues.months.length} months){dues.employee_share_waived ? " — employee's share waived" : ""}</h3>
        <dl className="kv">{LABELS.map(([k, label]) => <div key={k}><dt>{label}</dt><dd>{k === "TOTAL" ? <strong>{rupees(dues.totals_paise[k])}</strong> : rupees(dues.totals_paise[k])}</dd></div>)}</dl>
        {dues.trrn ? <p role="status">Challan {dues.trrn} raised: pay it (Payments › challan status); the member&apos;s account is credited when it is paid.</p> : null}</div> : null}
      <div className="actions"><button type="submit" className="primary" disabled={busy || !!dues?.trrn}>{dues ? "Declare and raise the challan" : "Work out the dues"}</button></div>
    </form> : <p className="muted">No employee to declare: register a left-out employee first.</p>) : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </section>;
}
