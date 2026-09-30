import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, command, getSession, newIdempotencyKey, rupees, type Envelope } from "../../api/client";
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
type ComplianceStatus = "FILED_AND_PAID_ON_TIME" | "PAID_LATE" | "FILED_NOT_PAID" | "NOT_FILED";
const complianceLabels: Record<ComplianceStatus, string> = {
  FILED_AND_PAID_ON_TIME: "Filed and paid on time", PAID_LATE: "Paid late",
  FILED_NOT_PAID: "Filed but not paid", NOT_FILED: "Not filed",
};
interface ComplianceSummary {
  establishment_id: string; as_of: string; counts: Record<ComplianceStatus, number>;
  months: { wage_month: string; due_date: string; status: ComplianceStatus; paid_on: string | null;
    days_late: number; total_paise: number }[];
}
interface VishwasApplication {
  application_id: string; demand_ids: string[]; damages_paise: number; revised_paise: number | null;
  state: "SUBMITTED" | "APPROVED" | "REJECTED"; decision_note: string | null;
}
interface VishwasData {
  applications: VishwasApplication[];
  open_14b_demands: { demand_id: string; wage_month: string; amount_paise: number; working: string }[];
  settlement_share_pct: number;
}

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
  const [selectedDemands, setSelectedDemands] = useState<string[]>([]);
  const [declaration, setDeclaration] = useState(false);
  const [pendingPayments, setPendingPayments] = useState<string[]>([]);
  const paymentReload = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (paymentReload.current !== null) clearTimeout(paymentReload.current); }, []);

  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const signatory = session.data?.stakeholder === "employer.signatory";
  const dashboard = useQuery({ queryKey: ["returns-dashboard"], retry: false,
    queryFn: () => api<Envelope<MonthReturn[]>>(`${base}/returns/dashboard`) });
  const demands = useQuery({ queryKey: ["employer-demands"], retry: false,
    queryFn: () => api<Envelope<Demands>>(`${base}/demands`) });
  const establishment = useQuery({ queryKey: ["direct-challan-establishment"], enabled: signatory, retry: false,
    queryFn: () => api<Envelope<{ establishment_id: string }>>(base) });
  const compliance = useQuery({ queryKey: ["employer-compliance-summary"], retry: false,
    queryFn: () => api<Envelope<ComplianceSummary>>(`${base}/compliance-summary`) });
  const vishwas = useQuery({ queryKey: ["employer-vishwas-applications"], retry: false,
    queryFn: () => api<Envelope<VishwasData>>(`${base}/vishwas-applications`) });

  async function reloadCompliance() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["employer-demands"] }),
      qc.invalidateQueries({ queryKey: ["employer-compliance-summary"] }),
      qc.invalidateQueries({ queryKey: ["employer-vishwas-applications"] }),
    ]);
  }

  async function payDemand(demand: Demand) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const token = await stepUp.ask({ action: "pay-demand", resourceId: demand.demand_id,
        amountPaise: demand.amount_paise, summary: `Pay demand ${demand.demand_id} for ${rupees(demand.amount_paise)}` });
      if (!token) return;
      await command("POST", `${base}/demands/${encodeURIComponent(demand.demand_id)}/payment-intents`,
        { channel: "NET_BANKING", demo_scenario: "SUCCESS" }, { stepUpToken: token, idempotencyKey: newIdempotencyKey() });
      setPendingPayments((current) => [...current, demand.demand_id]);
      setNotice(`Payment initiated for ${demand.demand_id}. The mock bank confirms in a few seconds; demands will refresh shortly.`);
      await reloadCompliance();
      if (paymentReload.current !== null) clearTimeout(paymentReload.current);
      paymentReload.current = setTimeout(() => {
        paymentReload.current = null;
        void reloadCompliance().catch((cause: unknown) => setError(cause));
      }, 3000);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  async function applyVishwas(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setError(null); setNotice(null);
    try {
      const chosen = vishwas.data?.data.open_14b_demands.filter((item) => selectedDemands.includes(item.demand_id)) ?? [];
      if (!chosen.length || !declaration) throw new Error("Choose at least one open 14B demand and accept the declaration.");
      const result = await command<Envelope<VishwasApplication & { estimated_settlement_paise: number }>>(
        "POST", `${base}/vishwas-applications`, { demand_ids: chosen.map((item) => item.demand_id), declaration: true });
      setNotice(`Application ${result.data.application_id} submitted. Illustrative estimated settlement: ${rupees(result.data.estimated_settlement_paise)}.`);
      setSelectedDemands([]); setDeclaration(false);
      await reloadCompliance();
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

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
        reloadCompliance(),
        qc.invalidateQueries({ queryKey: ["challans"] }),
      ]);
      setReason("");
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <main className="stack">
    <PageHeader eyebrow="Employer services" title="Returns, demands and direct challans" current="Returns dashboard"
      description="Track monthly returns, review demands, and raise direct challans." />
    <ProblemMessage error={error ?? session.error ?? dashboard.error ?? demands.error ?? establishment.error ?? compliance.error ?? vishwas.error} />
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
        {signatory ? <th scope="col">Payment</th> : null}
      </tr></thead><tbody>{demands.data.data.items.map((demand) => <tr key={demand.demand_id}>
        <th scope="row">{demand.demand_id}</th><td>{demand.kind === "DAMAGES_14B" ? "14B damages" : "7Q interest"}</td>
        <td><code>{demand.trrn}</code></td><td>{demand.wage_month}</td><td>{rupees(demand.amount_paise)}</td>
        <td>{demand.days_late}</td><td>{demand.working}</td><td>{demand.state.replaceAll("_", " ")}
          {demand.settled_by ? ` · ${demand.settled_by}` : ""}</td>
        {signatory ? <td>{demand.state === "OPEN" ? <button type="button"
          disabled={busy || !!stepUp.request || pendingPayments.includes(demand.demand_id)}
          aria-label={`Pay now for demand ${demand.demand_id}`} onClick={() => void payDemand(demand)}>
          {pendingPayments.includes(demand.demand_id) ? "Payment pending" : "Pay now"}</button> : "—"}</td> : null}
      </tr>)}</tbody></table></div> : demands.data ? <p className="muted">No demands recorded.</p> : null}
    </section>

    <section className="card stack" aria-labelledby="compliance-summary-heading"><h2 id="compliance-summary-heading">Compliance summary</h2>
      {compliance.isLoading ? <p role="status">Loading compliance summary…</p> : null}
      {compliance.data ? <><p>{compliance.data.data.establishment_id} · As of {compliance.data.data.as_of}</p>
        <dl>{(Object.keys(complianceLabels) as ComplianceStatus[]).map((status) => <div key={status}>
          <dt>{complianceLabels[status]}</dt><dd>{compliance.data.data.counts[status] ?? 0}</dd></div>)}</dl>
        <p className="muted">Showing up to the 24 most recent wage months.</p>
        {compliance.data.data.months.length ? <div className="table-scroll"><table><thead><tr>
          <th scope="col">Wage month</th><th scope="col">Due date</th><th scope="col">Status</th>
          <th scope="col">Paid on</th><th scope="col">Days late</th><th scope="col">Total</th>
        </tr></thead><tbody>{[...compliance.data.data.months].sort((a, b) => b.wage_month.localeCompare(a.wage_month)).slice(0, 24).map((month) =>
          <tr key={month.wage_month}><th scope="row">{month.wage_month}</th><td>{month.due_date}</td>
            <td>{complianceLabels[month.status]}</td><td>{month.paid_on ?? "—"}</td><td>{month.days_late}</td>
            <td>{rupees(month.total_paise)}</td></tr>)}</tbody></table></div> : <p className="muted">No compliance months recorded.</p>}
      </> : null}
    </section>

    <section className="card stack" aria-labelledby="vishwas-heading"><h2 id="vishwas-heading">VISHWAS — settling 14B damages</h2>
      <p className="muted">This settlement is illustrative. 7Q interest is not covered.</p>
      {vishwas.isLoading ? <p role="status">Loading VISHWAS applications…</p> : null}
      {vishwas.data ? <p>Illustrative settlement share: {vishwas.data.data.settlement_share_pct}% of selected 14B damages, subject to approval.</p> : null}
      {vishwas.data?.data.applications.length ? <div className="table-scroll"><table><thead><tr>
        <th scope="col">Application</th><th scope="col">Demands</th><th scope="col">Damages</th>
        <th scope="col">Revised amount</th><th scope="col">State</th><th scope="col">Decision note</th>
      </tr></thead><tbody>{vishwas.data.data.applications.map((item) => <tr key={item.application_id}>
        <th scope="row">{item.application_id}</th><td>{item.demand_ids.join(", ")}</td><td>{rupees(item.damages_paise)}</td>
        <td>{rupees(item.revised_paise)}</td><td>{item.state}</td><td>{item.decision_note ?? "—"}</td>
      </tr>)}</tbody></table></div> : vishwas.data ? <p className="muted">No VISHWAS applications recorded.</p> : null}
      {signatory && vishwas.data ? <form className="stack" onSubmit={(e) => void applyVishwas(e)}>
        <fieldset><legend>Open 14B demands</legend>
          {vishwas.data.data.open_14b_demands.length ? vishwas.data.data.open_14b_demands.map((item) => <label key={item.demand_id}>
            <input type="checkbox" checked={selectedDemands.includes(item.demand_id)} disabled={busy}
              onChange={(e) => setSelectedDemands((current) => e.target.checked ? [...current, item.demand_id] : current.filter((id) => id !== item.demand_id))} />
            {item.demand_id} · {item.wage_month} · {rupees(item.amount_paise)} · {item.working}
          </label>) : <p className="muted">No open 14B demands available.</p>}
        </fieldset>
        <label><input type="checkbox" required checked={declaration} disabled={busy}
          onChange={(e) => setDeclaration(e.target.checked)} /> I accept the settlement terms; illustrative</label>
        <div className="actions"><button type="submit" className="primary"
          disabled={busy || !!stepUp.request || !selectedDemands.length || !declaration}>Apply for settlement</button></div>
      </form> : null}
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
