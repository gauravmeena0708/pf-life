import { useTranslation } from "react-i18next";
import { rupees } from "../../api/client";
import { statusLabel } from "../statusLabel";
import "./ReturnsView.css";

export interface TrustFlag { flag_id: string; category: "A" | "B" | "C"; code: string; text: string; action: string | null; action_note?: string | null }
export interface TrustReturn { return_id: string; wage_month: string; version: number; state: string; score: number; parts: Record<string, number>; flags: TrustFlag[];
  employees_opening: number; joined: number; left: number; excluded: number; contract_trust: number; contract_elsewhere: number; direct_exempted: number; direct_unexempted: number; international_workers: number; disabled_workers: number;
  pf_wages_paise: number; employee_share_paise: number; employer_share_paise: number; due_paise: number; transfers: { date: string; amount_paise: number }[]; interest_paid_paise: number;
  claims_opening: number; claims_received: number; claims_within_days: number; claims_beyond_days: number; claims_pending: number; pending_reasons: string | null;
  grievances_opening: number; grievances_received: number; grievances_disposed: number; interest_rate_declared_bp: number; investible_corpus_paise: number; invested_paise: number;
  accounts_audited: boolean; member_balances_total_paise: number | null }
const parts: [string, string][] = [["transfer_before_due_date", "Transfer before due date"], ["investment", "Investment"], ["remittance", "Remittance"], ["interest_declared", "Interest declared"], ["claim_settlement", "Claim settlement"], ["audit_of_accounts", "Audit of accounts"]];
export function FlagPill({ category }: { category: TrustFlag["category"] }) { return <span className={`trust-flag trust-flag-${category}`} aria-label={`Category ${category}`}>Category {category}</span>; }
export function ReturnsView({ returns, children }: { returns: TrustReturn[]; children?: (item: TrustReturn) => React.ReactNode }) {
  const { t } = useTranslation();
  if (!returns.length) return <p className="muted">No monthly returns filed.</p>;
  return <div className="stack">{returns.map((item) => <article key={item.return_id} className={`profile-card stack trust-return ${item.state === "SUPERSEDED" ? "trust-superseded" : ""}`} aria-label={`Return ${item.wage_month} version ${item.version}`}>
    <h3>{item.wage_month} · {item.score}/600 <span className="state-pill">{statusLabel(item.state, t)}</span></h3>
    <div className="trust-parts">{parts.map(([key, label]) => <div key={key} className="trust-part"><span>{label}</span><progress value={item.parts[key] ?? 0} max="100" aria-label={label} /><strong>{item.parts[key] ?? 0}/100</strong></div>)}</div>
    <details><summary>Return details</summary><dl className="kv">
      <dt>Employees</dt><dd>Opening {item.employees_opening}; joined {item.joined}; left {item.left}; excluded {item.excluded}; contract under trust {item.contract_trust}; contract elsewhere {item.contract_elsewhere}; direct exempted {item.direct_exempted}; direct unexempted {item.direct_unexempted}; international {item.international_workers}; disabled {item.disabled_workers}</dd>
      <dt>PF wages</dt><dd>{rupees(item.pf_wages_paise)}</dd><dt>Employee share</dt><dd>{rupees(item.employee_share_paise)}</dd><dt>Employer share</dt><dd>{rupees(item.employer_share_paise)}</dd><dt>Due</dt><dd>{rupees(item.due_paise)}</dd>
      <dt>Transfers</dt><dd>{item.transfers.map((transfer) => `${transfer.date}: ${rupees(transfer.amount_paise)}`).join("; ") || "None"}</dd><dt>Late transfer interest</dt><dd>{rupees(item.interest_paid_paise)}</dd>
      <dt>Claims</dt><dd>Opening {item.claims_opening}; received {item.claims_received}; within 10 days {item.claims_within_days}; beyond {item.claims_beyond_days}; pending {item.claims_pending}. {item.pending_reasons}</dd>
      <dt>Grievances</dt><dd>Opening {item.grievances_opening}; received {item.grievances_received}; disposed {item.grievances_disposed}</dd>
      <dt>Interest declared</dt><dd>{item.interest_rate_declared_bp / 100}%</dd><dt>Investible corpus</dt><dd>{rupees(item.investible_corpus_paise)}</dd><dt>Invested</dt><dd>{rupees(item.invested_paise)}</dd>
      <dt>Accounts audited</dt><dd>{item.accounts_audited ? "Yes" : "No"}</dd><dt>Member balances</dt><dd>{item.member_balances_total_paise == null ? "Not reported" : rupees(item.member_balances_total_paise)}</dd>
    </dl></details>
    {item.flags.length ? <ul className="trust-flags">{item.flags.map((flag) => <li key={flag.flag_id}><FlagPill category={flag.category} /> {statusLabel(flag.code, t)} · {flag.text} {flag.action ? <span className="state-pill">{statusLabel(flag.action, t)}</span> : null}</li>)}</ul> : <p className="muted small">No flags.</p>}
    {children?.(item)}
  </article>)}</div>;
}
