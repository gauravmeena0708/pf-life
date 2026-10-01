import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, getSession, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import type { BoardPack, Meeting } from "./FinanceTypes";
import "./FinancePages.css";

const defaults = (role?: string): Meeting => role === "gov.ec" ? "EC" : role === "gov.fiac" ? "FIAC" : "CBT";
function Metrics({ items }: { items: { label: string; value: string | number }[] }) {
  return <dl className="finance-metrics">{items.map(({ label, value }) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}
const percent = (value: number | null) => value === null ? "—" : `${value}%`;
const days = (value: number | null) => value === null ? "—" : `${value} days`;

export function BoardPacksPage() {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Meeting | null>(null);
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const role = session.data?.stakeholder;
  const allowed = ["gov.cbt", "gov.ec", "gov.fiac", "ho.cpfc"].includes(role ?? "");
  const meeting = selected ?? defaults(role);
  const result = useQuery({ queryKey: ["board-pack", meeting], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<BoardPack>>(`/api/v1/governance/board-packs?meeting=${meeting}`) });
  const data = result.data?.data;
  return <section className="stack finance-page"><PageHeader eyebrow="Governance" title="Board packs" description="Aggregate briefing for the selected meeting." current="Board packs" />
    <ProblemMessage error={session.error ?? result.error} />
    {session.isLoading ? <p role="status">Loading role…</p> : null}
    {session.data && !allowed ? <p className="pending-notice">Board packs are available to CBT, EC, FIAC and the CPFC.</p> : null}
    {allowed ? <><div className="finance-toolbar"><label>Meeting<select value={meeting} onChange={(e) => setSelected(e.target.value as Meeting)}>{(["CBT", "EC", "FIAC"] as const).map((code) => <option key={code} value={code}>{statusLabel(code, t)}</option>)}</select></label><button type="button" onClick={() => window.print()} disabled={!data}>Print</button></div>
      <p className="finance-note">Aggregates only — no personal data</p>
      {result.isLoading ? <p role="status">Loading board pack…</p> : null}
      {data ? <><p className="muted">Generated at {new Date(data.generated_at).toLocaleString("en-IN")}</p>
        <section className="card stack"><h2>Contributions</h2><Metrics items={[{ label: "Wage months", value: data.sections.contributions.wage_months }, { label: "Returns filed", value: data.sections.contributions.returns_filed }, { label: "Returns paid", value: data.sections.contributions.returns_paid }, { label: "Amount paid", value: rupees(data.sections.contributions.amount_paise) }]} /></section>
        <section className="card stack"><h2>Claims</h2><Metrics items={[{ label: "Received", value: data.sections.claims.received }, { label: "Settled", value: data.sections.claims.settled }, { label: "Rejected", value: data.sections.claims.rejected }, { label: "Average time to settle", value: days(data.sections.claims.average_days_to_settle) }, { label: "Settled within 20 days", value: percent(data.sections.claims.share_settled_within_20_days_pct) }]} /></section>
        <section className="card stack"><h2>Grievances</h2><Metrics items={[{ label: "Received", value: data.sections.grievances.received }, { label: "Resolved", value: data.sections.grievances.resolved }, { label: "Pending", value: data.sections.grievances.pending }, { label: "Average time to resolve", value: days(data.sections.grievances.average_days_to_resolve) }]} /></section>
        <section className="card stack"><h2>Investments</h2><p className="muted">As of {data.sections.investments.as_of}</p><Metrics items={[{ label: "Book value", value: rupees(data.sections.investments.totals.book_value_paise) }, { label: "Market value", value: rupees(data.sections.investments.totals.market_value_paise) }, { label: "Unrealised gain", value: rupees(data.sections.investments.totals.unrealised_gain_paise) }]} />
          <div className="table-scroll"><table className="finance-table"><thead><tr><th scope="col">Fund</th><th scope="col" className="amount">Book value</th><th scope="col" className="amount">Market value</th><th scope="col" className="amount">Gain</th></tr></thead><tbody>{data.sections.investments.funds.map((fund) => <tr key={fund.fund}><th scope="row">{fund.fund}</th><td className="amount">{rupees(fund.totals.book_value_paise)}</td><td className="amount">{rupees(fund.totals.market_value_paise)}</td><td className="amount">{rupees(fund.totals.unrealised_gain_paise)}</td></tr>)}</tbody></table></div>
          {data.sections.investments.pattern_flags?.length ? <div className="table-scroll"><table className="finance-table"><caption>Investment pattern flags</caption><thead><tr><th scope="col">Fund</th><th scope="col">Asset class</th><th scope="col">Share</th><th scope="col">Band</th><th scope="col">Flag</th></tr></thead><tbody>{data.sections.investments.pattern_flags.map((flag) => <tr key={`${flag.fund}-${flag.asset_class}`}><th scope="row">{flag.fund}</th><td>{statusLabel(flag.asset_class, t)}</td><td>{flag.share_pct}%</td><td>{flag.pattern_band.min_pct}–{flag.pattern_band.max_pct}%</td><td><span className={`finance-pill${flag.flag === "ABOVE" || flag.flag === "BELOW" ? " alert" : ""}`}>{statusLabel(flag.flag, t)}</span></td></tr>)}</tbody></table></div> : null}</section>
        <p className="finance-note">{data.note}</p></> : null}</> : null}
  </section>;
}
