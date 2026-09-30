import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, command, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const base = "/api/v1/employers/me";

interface ReturnEntry {
  type: string; state: string; trrn: string | null; challan: string | null;
  total_paise: number | null; paid_on: string | null;
}
interface MonthReturn {
  wage_month: string; due_date: string; status: "PAID" | "AWAITING_PAYMENT" | "NOT_FILED" | "IN_PREPARATION";
  paid_late: boolean; paid_paise: number; regular: ReturnEntry | null; additional: ReturnEntry[];
}
interface Demand {
  demand_id: string; kind: "DAMAGES_14B" | "INTEREST_7Q"; trrn: string; wage_month: string;
  amount_paise: number; days_late: number; working: string; state: "OPEN" | "KNOCKED_OFF"; settled_by: string | null;
}
interface Demands { items: Demand[]; open_paise: number; note: string }
interface DirectChallan { trrn: string; total_paise: number }

function ReturnDetails({ entry }: { entry: ReturnEntry }) {
  return <span>{entry.type} · {entry.state.replaceAll("_", " ")}
    {entry.trrn ? <> · TRRN <code>{entry.trrn}</code></> : null}
    {entry.challan ? <> · {entry.challan}</> : null}
    {entry.total_paise != null ? <> · {rupees(entry.total_paise)}</> : null}
    {entry.paid_on ? <> · paid {entry.paid_on}</> : null}</span>;
}

function toPaise(value: string): number {
  return Math.round(Number(value) * 100);
}

export function ReturnsPage() {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState<"ADMIN_CHARGES" | "MISC_14B_7Q">("ADMIN_CHARGES");
  const [admin, setAdmin] = useState("");
  const [damages, setDamages] = useState("");
  const [interest, setInterest] = useState("");
  const [reason, setReason] = useState("");
  const [created, setCreated] = useState<DirectChallan | null>(null);

  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const signatory = session.data?.stakeholder === "employer.signatory";
  const dashboard = useQuery({ queryKey: ["returns-dashboard"], retry: false,
    queryFn: () => api<Envelope<MonthReturn[]>>(`${base}/returns/dashboard`) });
  const demands = useQuery({ queryKey: ["employer-demands"], retry: false,
    queryFn: () => api<Envelope<Demands>>(`${base}/demands`) });
  const establishment = useQuery({ queryKey: ["direct-challan-establishment"], enabled: signatory, retry: false,
    queryFn: () => api<Envelope<{ establishment_id: string }>>(base) });

  function fillDemands() {
    const open = demands.data?.data.items.filter((item) => item.state === "OPEN") ?? [];
    setDamages(String(open.filter((item) => item.kind === "DAMAGES_14B").reduce((sum, item) => sum + item.amount_paise, 0) / 100));
    setInterest(String(open.filter((item) => item.kind === "INTEREST_7Q").reduce((sum, item) => sum + item.amount_paise, 0) / 100));
  }

  async function raiseChallan(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const establishmentId = establishment.data?.data.establishment_id;
    const adminPaise = kind === "ADMIN_CHARGES" ? toPaise(admin) : 0;
    const damagesPaise = kind === "MISC_14B_7Q" ? toPaise(damages) : 0;
    const interestPaise = kind === "MISC_14B_7Q" ? toPaise(interest) : 0;
    const total = adminPaise + damagesPaise + interestPaise;
    if (!establishmentId || !Number.isSafeInteger(total) || total <= 0 || total % 100 !== 0) {
      setError(new Error("Enter a positive total in whole rupees and wait for establishment details to load."));
      return;
    }
    if (reason.trim().length < 5) { setError(new Error("Enter a reason of at least 5 characters.")); return; }
    const token = await stepUp.ask({ action: "raise-direct-challan", resourceId: establishmentId,
      amountPaise: total, summary: `Raise ${kind === "ADMIN_CHARGES" ? "administrative charges" : "14B / 7Q"} challan for ${rupees(total)}` });
    if (!token) return;
    setBusy(true); setError(null); setNotice(null); setCreated(null);
    try {
      const result = await command<Envelope<DirectChallan>>("POST", `${base}/direct-challans`,
        { kind, admin_paise: adminPaise, damages_14b_paise: damagesPaise, interest_7q_paise: interestPaise, reason: reason.trim() },
        { stepUpToken: token });
      setCreated(result.data);
      setNotice(`Direct challan ${result.data.trrn} raised for ${rupees(result.data.total_paise)}.`);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["returns-dashboard"] }),
        qc.invalidateQueries({ queryKey: ["employer-demands"] }),
        qc.invalidateQueries({ queryKey: ["challans"] }),
      ]);
      setReason("");
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <main className="stack">
    <PageHeader eyebrow="Employer services" title="Returns, demands and direct challans" current="Returns dashboard"
      description="Track monthly returns, review demands, and raise direct challans." />
    <ProblemMessage error={error ?? session.error ?? dashboard.error ?? demands.error ?? establishment.error} />
    {notice ? <p role="status" className="ok">{notice}</p> : null}

    <section className="card stack" aria-labelledby="returns-dashboard-heading"><h2 id="returns-dashboard-heading">Returns dashboard</h2>
      {dashboard.isLoading ? <p role="status">Loading returns…</p> : null}
      {dashboard.data?.data.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Wage month</th><th scope="col">Due date</th><th scope="col">Status</th>
        <th scope="col">Regular return</th><th scope="col">Additional returns</th><th scope="col">Paid</th>
      </tr></thead><tbody>{dashboard.data.data.map((month) => <tr key={month.wage_month}>
        <th scope="row">{month.wage_month}</th><td>{month.due_date}</td><td>{month.status.replaceAll("_", " ")}
          {month.paid_late ? " · paid late" : ""}</td>
        <td>{month.regular ? <ReturnDetails entry={month.regular} /> : "—"}</td>
        <td>{month.additional.length ? <ul>{month.additional.map((entry, index) => <li key={`${entry.trrn ?? entry.type}-${index}`}>
          <ReturnDetails entry={entry} /></li>)}</ul> : "—"}</td><td>{rupees(month.paid_paise)}</td>
      </tr>)}</tbody></table></div> : dashboard.data ? <p className="muted">No returns yet.</p> : null}
    </section>

    <section className="card stack" aria-labelledby="demands-heading"><h2 id="demands-heading">14B / 7Q demands</h2>
      {demands.isLoading ? <p role="status">Loading demands…</p> : null}
      {demands.data ? <><p><strong>Total open: {rupees(demands.data.data.open_paise)}</strong></p>
        <p className="muted">{demands.data.data.note}</p></> : null}
      {demands.data?.data.items.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Demand</th><th scope="col">Kind</th><th scope="col">TRRN</th><th scope="col">Wage month</th>
        <th scope="col">Amount</th><th scope="col">Days late</th><th scope="col">Working</th><th scope="col">State</th>
      </tr></thead><tbody>{demands.data.data.items.map((demand) => <tr key={demand.demand_id}>
        <th scope="row">{demand.demand_id}</th><td>{demand.kind === "DAMAGES_14B" ? "14B damages" : "7Q interest"}</td>
        <td><code>{demand.trrn}</code></td><td>{demand.wage_month}</td><td>{rupees(demand.amount_paise)}</td>
        <td>{demand.days_late}</td><td>{demand.working}</td><td>{demand.state.replaceAll("_", " ")}
          {demand.settled_by ? ` · ${demand.settled_by}` : ""}</td>
      </tr>)}</tbody></table></div> : demands.data ? <p className="muted">No demands recorded.</p> : null}
    </section>

    {signatory ? <section className="card stack" aria-labelledby="direct-challan-heading"><h2 id="direct-challan-heading">Direct challan</h2>
      <form className="stack" onSubmit={(e) => void raiseChallan(e)}>
        <label>Kind <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="ADMIN_CHARGES">Administrative charges</option><option value="MISC_14B_7Q">14B damages and 7Q interest</option>
        </select></label>
        {kind === "ADMIN_CHARGES" ? <label>Administrative charges (₹)
          <input type="number" min="1" step="1" required value={admin} onChange={(e) => setAdmin(e.target.value)} /></label> : <>
          <div className="form-row"><label>14B damages (₹)<input type="number" min="0" step="1" required value={damages}
            onChange={(e) => setDamages(e.target.value)} /></label>
            <label>7Q interest (₹)<input type="number" min="0" step="1" required value={interest}
              onChange={(e) => setInterest(e.target.value)} /></label></div>
          <div className="actions"><button type="button" disabled={!demands.data || busy} onClick={fillDemands}>Fill from open demands</button></div>
        </>}
        <label>Reason <input required minLength={5} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <div className="actions"><button type="submit" className="primary" disabled={busy || !establishment.data}>Raise direct challan</button></div>
      </form>
      {created ? <p role="status" className="ok">TRRN <code>{created.trrn}</code> · {rupees(created.total_paise)}. Pay it from the ECR page’s challan list.</p> : null}
    </section> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </main>;
}
