import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import "./RankingsPage.css";

/** Returns are due by the 15th of the following month, so the latest month to look at is the last one. */
const lastMonth = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
export interface Ranking { rank: number; establishment_id: string; legal_name: string; office_id: string; wage_month: string; score: number; flags: string[] }
export function RankingsTable({ onSelect }: { onSelect?: (item: Ranking) => void }) {
  const { t } = useTranslation(); const [month, setMonth] = useState(lastMonth);
  const rankings = useQuery({ queryKey: ["exempted-rankings", month], retry: false, queryFn: () => api<Envelope<{ rankings: Ranking[] }>>(`/api/v1/office/exempted/rankings?month=${month}`) });
  return <section className="card stack" aria-labelledby="exempted-rankings-heading"><h2 id="exempted-rankings-heading">Exempted establishments</h2>
    <label>Wage month<input type="month" value={month} max={new Date().toISOString().slice(0, 7)} onChange={(e) => setMonth(e.target.value)} /></label>
    <ProblemMessage error={rankings.error} />{rankings.isLoading ? <p role="status">Loading rankings…</p> : null}
    {rankings.data ? <div className="table-scroll"><table><thead><tr><th scope="col">Rank</th><th scope="col">Establishment</th><th scope="col">Office</th><th scope="col">Score / 600</th><th scope="col">Flags</th></tr></thead>
      <tbody>{rankings.data.data.rankings.map((item) => <tr key={item.establishment_id}><td>{item.rank}</td><th scope="row">{onSelect ? <button type="button" className="trust-ranking-select" onClick={() => onSelect(item)}>{item.legal_name}</button> : item.legal_name}<span className="muted small"> · {item.establishment_id}</span></th>
        <td>{item.office_id}</td><td>{item.score}</td><td>{item.flags.length ? item.flags.map((flag, index) => <span className="state-pill" key={`${flag}-${index}`}>{statusLabel(flag, t)}</span>) : "—"}</td></tr>)}</tbody></table></div> : null}
    {rankings.data?.data.rankings.length === 0 ? <p className="muted">No exempted establishments for this month.</p> : null}</section>;
}
export function RankingsPage() { return <section className="stack"><PageHeader eyebrow="HO Exemption Division" title="Exempted establishments ranking" current="Exempted establishments ranking" description="Monthly performance across all offices." /><RankingsTable /></section>; }
