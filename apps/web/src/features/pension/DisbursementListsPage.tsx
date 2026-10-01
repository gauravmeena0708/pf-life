import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

type Item = { ppo_id: string; name_masked: string; account_last4: string; amount_paise: number };
type Bank = { bank: string; pensioners: number; amount_paise: number; items: Item[] };
type Lists = { month: string; banks: Bank[]; totals: { pensioners: number; amount_paise: number }; note: string };
const lastMonth = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

export function DisbursementListsPage() {
  const [month, setMonth] = useState(lastMonth);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = session.data?.stakeholder === "fo.pension_disbursement";
  const lists = useQuery({ queryKey: ["pension-disbursement-lists", month], enabled: allowed && !!month, retry: false,
    queryFn: () => api<Envelope<Lists>>(`/api/v1/office/pensions/disbursement-lists?month=${encodeURIComponent(month)}`) });
  const data = lists.data?.data;
  return <section className="stack" aria-labelledby="disbursement-lists-heading">
    <PageHeader id="disbursement-lists-heading" eyebrow="Pension administration" title="Disbursement lists"
      description="Bank-wise monthly pension payment lists for the field office." current="Disbursement lists" />
    <ProblemMessage error={session.error ?? lists.error} />
    {session.data && !allowed ? <p className="pending-notice">This service is available to pension disbursement staff.</p> : null}
    {allowed ? <section className="card stack"><div className="form-row"><label>Payment month<input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></label></div>
      {lists.isLoading ? <p role="status">Loading disbursement lists…</p> : null}
      {data ? <><div className="actions"><button type="button" onClick={() => window.print()}>Print</button></div>
        <p>{data.month} · {data.totals.pensioners} pensioners · {rupees(data.totals.amount_paise)} total</p>
        {data.banks.length ? data.banks.map((bank) => <section className="stack" key={bank.bank} aria-label={`Bank ${bank.bank}`}>
          <h2>Bank {bank.bank}</h2><div className="table-scroll"><table><thead><tr><th scope="col">PPO</th><th scope="col">Name</th><th scope="col">Account last 4</th><th scope="col">Amount</th></tr></thead>
            <tbody>{bank.items.map((item) => <tr key={item.ppo_id}><td>{item.ppo_id}</td><td>{item.name_masked}</td><td>{item.account_last4}</td><td>{rupees(item.amount_paise)}</td></tr>)}</tbody>
            <tfoot><tr><th scope="row" colSpan={3}>{bank.pensioners} pensioners</th><td>{rupees(bank.amount_paise)}</td></tr></tfoot></table></div>
        </section>) : <p>No payments for this month.</p>}
        <p className="muted small">{data.note}</p></> : null}
    </section> : null}
  </section>;
}
