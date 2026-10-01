import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, command, newIdempotencyKey, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { ReturnsView, type TrustReturn } from "./ReturnsView";
import "./MonthlyReturn.css";

const employeeFields = [["employees_opening", "Opening"], ["joined", "Joined"], ["left", "Left"], ["excluded", "Excluded"], ["contract_trust", "Contract under the trust"], ["contract_elsewhere", "Contract elsewhere"], ["direct_exempted", "Direct exempted"], ["direct_unexempted", "Direct unexempted"], ["international_workers", "International workers"], ["disabled_workers", "Disabled workers"]] as const;
const moneyFields = [["pf_wages", "PF wages"], ["employee_share", "Employee share"], ["employer_share", "Employer share"], ["interest_paid", "Interest paid for late transfer"], ["investible_corpus", "Investible corpus"], ["invested", "Invested"]] as const;
const claimFields = [["claims_opening", "Claims opening"], ["claims_received", "Claims received"], ["claims_within_days", "Settled within 10 days"], ["claims_beyond_days", "Settled beyond 10 days"], ["grievances_opening", "Grievances opening"], ["grievances_received", "Grievances received"], ["grievances_disposed", "Grievances disposed"]] as const;
const number = (f: FormData, key: string) => Number(f.get(key) || 0);
const paise = (f: FormData, key: string) => Math.round(number(f, key) * 100);
export function MonthlyReturn() {
  const qc = useQueryClient(); const [error, setError] = useState<unknown>(null); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const [employees, setEmployees] = useState<Record<string, number>>({}); const [shares, setShares] = useState({ employee_share: 0, employer_share: 0 });
  const [claims, setClaims] = useState<Record<string, number>>({}); const [transfers, setTransfers] = useState([{ date: "", amount: "" }]);
  const returns = useQuery({ queryKey: ["trust-returns"], retry: false, queryFn: () => api<Envelope<{ returns: TrustReturn[] }>>("/api/v1/exempted/me/returns") });
  const headcount = (employees.employees_opening || 0) + (employees.joined || 0) - (employees.left || 0) - (employees.excluded || 0);
  const categories = (employees.contract_trust || 0) + (employees.contract_elsewhere || 0) + (employees.direct_exempted || 0) + (employees.direct_unexempted || 0);
  const pending = (claims.claims_opening || 0) + (claims.claims_received || 0) - (claims.claims_within_days || 0) - (claims.claims_beyond_days || 0);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const f = new FormData(event.currentTarget);
    if (headcount !== categories) { setError(new Error("Part C employee totals must balance.")); return; }
    if (pending < 0) { setError(new Error("Settled claims exceed available claims.")); return; }
    if (transfers.some((row) => Boolean(row.date) !== Boolean(row.amount))) { setError(new Error("Enter both date and amount for each transfer.")); return; }
    if (pending > 0 && !String(f.get("pending_reasons") || "").trim()) { setError(new Error("Give reasons for pending claims.")); return; }
    const body = { wage_month: String(f.get("wage_month")), ...Object.fromEntries(employeeFields.map(([key]) => [key, number(f, key)])),
      ...Object.fromEntries(moneyFields.map(([key]) => [`${key}_paise`, paise(f, key)])), due_paise: paise(f, "employee_share") + paise(f, "employer_share"),
      transfers: transfers.filter((row) => row.date && row.amount !== "").map((row) => ({ date: row.date, amount_paise: Math.round(Number(row.amount) * 100) })),
      ...Object.fromEntries(claimFields.map(([key]) => [key, number(f, key)])), pending_reasons: String(f.get("pending_reasons") || "").trim() || null,
      interest_rate_declared_bp: Math.round(number(f, "interest_rate_declared") * 100), accounts_audited: f.has("accounts_audited"),
      member_balances_total_paise: String(f.get("member_balances_total") || "").trim() ? paise(f, "member_balances_total") : null, revised: f.has("revised") };
    setBusy(true); setError(null); setNotice("");
    try { await command("POST", "/api/v1/exempted/me/returns", body, { idempotencyKey: newIdempotencyKey() }); setNotice("Monthly return filed."); await qc.invalidateQueries({ queryKey: ["trust-returns"] }); }
    catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <><section className="card stack" aria-labelledby="monthly-return-heading"><h2 id="monthly-return-heading">Monthly return</h2><ProblemMessage error={error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    <form className="stack" aria-label="File monthly return" onSubmit={(event) => void submit(event)}>
      <label>Wage month<input name="wage_month" type="month" required /></label>
      <fieldset><legend>Part C · Employees</legend><div className="form-row">{employeeFields.map(([key, label]) => <label key={key}>{label}<input name={key} type="number" min="0" step="1" defaultValue="0" required onChange={(e) => setEmployees((old) => ({ ...old, [key]: Number(e.target.value) }))} /></label>)}</div>
        <p role="status" aria-live="polite">Balance check: {headcount} employees; {categories} in categories — {headcount === categories ? "balanced" : "does not balance"}.</p></fieldset>
      <fieldset><legend>Part D · Contributions</legend><div className="form-row">{moneyFields.map(([key, label]) => <label key={key}>{label} (₹)<input name={key} type="number" min="0" step="0.01" defaultValue="0" required onChange={key === "employee_share" || key === "employer_share" ? (e) => setShares((old) => ({ ...old, [key]: Number(e.target.value) })) : undefined} /></label>)}</div>
        <p aria-live="polite">Due: ₹{(shares.employee_share + shares.employer_share).toFixed(2)}</p><h3>Transfers</h3>{transfers.map((row, index) => <div className="form-row" key={index}>
          <label>Transfer date<input type="date" value={row.date} onChange={(e) => setTransfers((old) => old.map((entry, i) => i === index ? { ...entry, date: e.target.value } : entry))} /></label>
          <label>Transfer amount (₹)<input type="number" min="0" step="0.01" value={row.amount} onChange={(e) => setTransfers((old) => old.map((entry, i) => i === index ? { ...entry, amount: e.target.value } : entry))} /></label>
          {transfers.length > 1 ? <button type="button" onClick={() => setTransfers((old) => old.filter((_, i) => i !== index))}>Remove transfer</button> : null}</div>)}
        <button type="button" onClick={() => setTransfers((old) => [...old, { date: "", amount: "" }])}>Add transfer</button></fieldset>
      <fieldset><legend>Claims and grievances</legend><div className="form-row">{claimFields.map(([key, label]) => <label key={key}>{label}<input name={key} type="number" min="0" step="1" defaultValue="0" required onChange={(e) => setClaims((old) => ({ ...old, [key]: Number(e.target.value) }))} /></label>)}</div>
        <p aria-live="polite">Claims pending: {pending}</p><label>Reasons for pending claims<textarea name="pending_reasons" required={pending > 0} /></label></fieldset>
      <div className="form-row"><label>Interest declared (%)<input name="interest_rate_declared" type="number" min="0" step="0.01" defaultValue="0" required /></label>
        <label>Total member balances (₹, optional)<input name="member_balances_total" type="number" min="0" step="0.01" /></label></div>
      <label><input name="accounts_audited" type="checkbox" /> Accounts audited</label><label><input name="revised" type="checkbox" /> Revise existing return for this month</label>
      <div className="actions"><button className="primary" disabled={busy || headcount !== categories || pending < 0} type="submit">File monthly return</button></div></form></section>
    <section className="card stack" aria-labelledby="returns-filed-heading"><h2 id="returns-filed-heading">Returns filed</h2><ProblemMessage error={returns.error} />{returns.isLoading ? <p role="status">Loading returns…</p> : null}<ReturnsView returns={returns.data?.data.returns ?? []} /></section></>;
}
