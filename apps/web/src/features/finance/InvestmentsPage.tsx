import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import type { Investments } from "./FinanceTypes";
import "./FinancePages.css";

export function InvestmentsPage() {
  const { t } = useTranslation();
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = ["ho.investment", "gov.fiac", "ho.fa_cao"].includes(session.data?.stakeholder ?? "");
  const result = useQuery({ queryKey: ["investments", asOf], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<Investments>>(`/api/v1/ho/finance/investments?as_of=${encodeURIComponent(asOf)}`) });
  const data = result.data?.data;
  return <section className="stack finance-page"><PageHeader eyebrow="Finance" title="Investments" description="Fund custody positions and investment pattern." current="Investments" />
    <ProblemMessage error={session.error ?? result.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !allowed ? <p className="pending-notice">Investment positions are available to authorised finance and FIAC roles.</p> : null}
    {allowed ? <><div className="finance-toolbar"><label>As of<input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label></div>
      {result.isLoading ? <p role="status">Loading investments…</p> : null}
      {data ? <>{data.funds.length ? data.funds.map((fund) => <section key={fund.fund} className="card stack"><h2>{fund.fund}</h2><div className="table-scroll"><table className="finance-table"><thead><tr><th scope="col">Asset class</th><th scope="col" className="amount">Book value</th><th scope="col" className="amount">Market value</th><th scope="col" className="amount">Gain</th><th scope="col" className="amount">Share</th><th scope="col">Pattern band</th><th scope="col">Flag</th></tr></thead>
        <tbody>{fund.asset_classes.map((item) => <tr key={item.asset_class}><th scope="row">{statusLabel(item.asset_class, t)}</th><td className="amount">{rupees(item.book_value_paise)}</td><td className="amount">{rupees(item.market_value_paise)}</td><td className="amount">{rupees(item.unrealised_gain_paise)}</td><td className="amount">{item.share_pct}%</td><td>{item.pattern_band.min_pct}–{item.pattern_band.max_pct}%</td><td><span className={`finance-pill${item.flag === "ABOVE" || item.flag === "BELOW" ? " alert" : ""}`}>{statusLabel(item.flag, t)}</span></td></tr>)}</tbody>
        <tfoot><tr><th scope="row">{fund.fund} total</th><td className="amount">{rupees(fund.totals.book_value_paise)}</td><td className="amount">{rupees(fund.totals.market_value_paise)}</td><td className="amount">{rupees(fund.totals.unrealised_gain_paise)}</td><td colSpan={3} /></tr></tfoot></table></div></section>) : <p className="muted">No fund positions available as of this date.</p>}
        <section className="card stack"><h2>All funds</h2><dl className="finance-metrics"><div><dt>Book value</dt><dd>{rupees(data.totals.book_value_paise)}</dd></div><div><dt>Market value</dt><dd>{rupees(data.totals.market_value_paise)}</dd></div><div><dt>Unrealised gain</dt><dd>{rupees(data.totals.unrealised_gain_paise)}</dd></div></dl><p><strong>Fund managers:</strong> {data.fund_managers.join(", ") || "None reported"}</p><p className="finance-note">{data.note}</p></section></> : null}</> : null}
  </section>;
}
