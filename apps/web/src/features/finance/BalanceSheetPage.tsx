import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import type { BalanceSheet } from "./FinanceTypes";
import "./FinancePages.css";

function StatementSide({ title, lines, total }: { title: string; lines: BalanceSheet["assets"]; total: number }) {
  return <section className="card stack"><h2>{title}</h2><div className="table-scroll"><table className="finance-table"><thead><tr><th scope="col">Account</th><th scope="col" className="amount">Amount</th></tr></thead>
    <tbody>{lines.map((line) => <tr key={line.code}><th scope="row">{line.name}</th><td className="amount">{rupees(line.amount_paise)}</td></tr>)}</tbody>
    <tfoot><tr><th scope="row">Total {title.toLowerCase()}</th><td className="amount">{rupees(total)}</td></tr></tfoot></table></div></section>;
}

export function BalanceSheetPage() {
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = ["gov.statutory_auditor", "ho.fa_cao"].includes(session.data?.stakeholder ?? "");
  const sheet = useQuery({ queryKey: ["balance-sheet", asOf], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<BalanceSheet>>(`/api/v1/ho/finance/balance-sheet?as_of=${encodeURIComponent(asOf)}`) });
  const data = sheet.data?.data;
  return <section className="stack finance-page"><PageHeader eyebrow="Finance" title="Balance sheet" description="Illustrative statement from the POC ledger." current="Balance sheet" />
    <ProblemMessage error={session.error ?? sheet.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !allowed ? <p className="pending-notice">This statement is available to the statutory auditor and HO Finance and Accounts.</p> : null}
    {allowed ? <><div className="finance-toolbar"><label>As of<input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label><button type="button" onClick={() => window.print()} disabled={!data}>Print</button></div>
      {sheet.isLoading ? <p role="status">Loading balance sheet…</p> : null}
      {data ? <><div className="finance-columns"><StatementSide title="Liabilities" lines={data.liabilities} total={data.total_liabilities_paise} /><StatementSide title="Assets" lines={data.assets} total={data.total_assets_paise} /></div>
        <p><span className={`finance-pill${data.balanced ? "" : " alert"}`}>{data.balanced ? "Balanced" : "Does not balance"}</span></p><p className="finance-note">{data.note}</p></> : null}</> : null}
  </section>;
}
