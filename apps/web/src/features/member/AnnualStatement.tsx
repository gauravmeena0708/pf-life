import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

type Shares = { employee: number; employer: number };
interface Account { account_link_id: string; establishment: string | null; opening: Shares; movements: Record<string, Shares>; closing: Shares; closing_total_paise: number }
interface Statement { financial_year: string; accounts: Account[]; note: string }
interface Taxable { taxable_interest_paise: number; non_taxable_interest_paise: number; employee_contributions_paise: number; threshold_paise: number;
  working: string; interest_credited: boolean; note: string }

const LABELS: Record<string, string> = { contributions: "Contributions", withdrawals: "Withdrawals", transfers: "Transfers",
  interest: "Interest", adjustments: "Adjustments and reversals" };

function yearsBack(n: number): string[] {
  const now = new Date();
  const start = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return Array.from({ length: n }, (_, i) => `${start - i}-${String((start - i + 1) % 100).padStart(2, "0")}`);
}

/** The annual statement for a financial year, and the taxable / non-taxable interest split (illustrative). */
export function AnnualStatement() {
  const years = yearsBack(3);
  const [fy, setFy] = useState(years[0]);
  const statement = useQuery({ queryKey: ["annual-statement", fy], retry: false,
    queryFn: () => api<Envelope<Statement>>(`/api/v1/members/me/annual-statements/${fy}`) });
  const tax = useQuery({ queryKey: ["taxable-interest", fy], retry: false,
    queryFn: () => api<Envelope<Taxable>>(`/api/v1/members/me/tax/taxable-interest?financialYear=${fy}`) });
  const both = (s: Shares) => `${rupees(s.employee)} + ${rupees(s.employer)}`;
  return (
    <section className="card stack" aria-labelledby="annual-statement-heading"><h2 id="annual-statement-heading">Annual statement</h2>
      <label>Financial year<select value={fy} onChange={(e) => setFy(e.target.value)}>{years.map((y) => <option key={y} value={y}>{y}</option>)}</select></label>
      <ProblemMessage error={statement.error ?? tax.error} />
      {statement.data?.data.accounts.map((a) => <div key={a.account_link_id} className="stack">
        <h3>{a.account_link_id}{a.establishment ? ` · ${a.establishment}` : ""}</h3>
        <div className="table-scroll"><table><caption className="muted small">Employee share + employer share</caption>
          <thead><tr><th scope="col">Item</th><th scope="col">Amount</th></tr></thead>
          <tbody><tr><th scope="row">Opening balance</th><td>{both(a.opening)}</td></tr>
            {Object.entries(a.movements).filter(([, s]) => s.employee || s.employer).map(([k, s]) => <tr key={k}><th scope="row">{LABELS[k] ?? k}</th><td>{both(s)}</td></tr>)}
            <tr><th scope="row">Closing balance</th><td><strong>{rupees(a.closing_total_paise)}</strong> ({both(a.closing)})</td></tr></tbody></table></div>
      </div>)}
      {statement.data ? <p className="muted small">{statement.data.data.note}</p> : null}
      {tax.data ? <div className="stack" role="region" aria-label="Taxable interest"><h3>Taxable interest (illustrative)</h3>
        <p>Taxable: <strong>{rupees(tax.data.data.taxable_interest_paise)}</strong> · not taxable: {rupees(tax.data.data.non_taxable_interest_paise)}.
          {tax.data.data.interest_credited ? "" : " Interest for this year is not credited yet."}</p>
        <p className="muted small">{tax.data.data.working} {tax.data.data.note}</p></div> : null}
    </section>
  );
}
