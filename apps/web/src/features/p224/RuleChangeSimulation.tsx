import { useState } from "react";
import { api, type Envelope } from "../../api/client";
import en from "../../i18n/p224-contribution-service.en.json";
import hi from "../../i18n/p224-contribution-service.hi.json";

type Result = { sample_size: number; total_change_paise: number; bands: { band: string; member_count: number; min_change_paise: number; median_change_paise: number; max_change_paise: number; gain_count: number; lose_count: number }[] };

export function RuleChangeSimulation() {
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const [year, setYear] = useState("2025-26");
  const [interest, setInterest] = useState("");
  const [ceiling, setCeiling] = useState("");
  const [employee, setEmployee] = useState("");
  const [employer, setEmployer] = useState("");
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState("");
  const t = language === "en" ? en : hi;
  async function run() {
    setError("");
    const body = { financial_year: year, ...(interest ? { interest_rate_bp: Number(interest) } : {}), ...(ceiling ? { wage_ceiling_paise: Number(ceiling) } : {}), ...(employee ? { employee_rate_bp: Number(employee) } : {}), ...(employer ? { employer_rate_bp: Number(employer) } : {}) };
    try { const response = await api<Envelope<Result>>("/api/v1/office/accounts/rule-change-simulations", { method: "POST", body: JSON.stringify(body) }); setResult(response.data); }
    catch { setError(t.error); }
  }
  return <main className="card stack" aria-labelledby="p224-title">
    <header><h1 id="p224-title">{t.title}</h1><label htmlFor="p224-language">{t.language}</label><select id="p224-language" value={language} onChange={(e) => setLanguage(e.target.value as "en" | "hi")}><option value="en">English</option><option value="hi">हिन्दी</option></select></header>
    <label htmlFor="p224-year">{t.year}<input id="p224-year" value={year} onChange={(e) => setYear(e.target.value)} /></label>
    <label htmlFor="p224-interest">{t.interest}<input id="p224-interest" type="number" value={interest} onChange={(e) => setInterest(e.target.value)} /></label>
    <label htmlFor="p224-ceiling">{t.ceiling}<input id="p224-ceiling" type="number" value={ceiling} onChange={(e) => setCeiling(e.target.value)} /></label>
    <label htmlFor="p224-employee">{t.employee}<input id="p224-employee" type="number" value={employee} onChange={(e) => setEmployee(e.target.value)} /></label>
    <label htmlFor="p224-employer">{t.employer}<input id="p224-employer" type="number" value={employer} onChange={(e) => setEmployer(e.target.value)} /></label>
    <button className="primary" type="button" onClick={() => void run()}>{t.run}</button>
    <p aria-live="polite" role={error ? "alert" : "status"}>{error || (result ? `${t.total}: ${result.total_change_paise} paise · ${t.members}: ${result.sample_size} · ${t.gain}: ${result.bands.reduce((sum, item) => sum + item.gain_count, 0)} · ${t.lose}: ${result.bands.reduce((sum, item) => sum + item.lose_count, 0)}` : "")}</p>
    {result ? <div className="table-scroll"><table><caption>{t.range} (paise)</caption><thead><tr><th scope="col">{t.band}</th><th scope="col">{t.count}</th><th scope="col">{t.range}</th><th scope="col">{t.gain}</th><th scope="col">{t.lose}</th></tr></thead>
      <tbody>{result.bands.map((item) => <tr key={item.band}><th scope="row">{t[item.band as "lower" | "middle" | "upper"] ?? item.band}</th><td>{item.member_count}</td><td>{item.min_change_paise} / {item.median_change_paise} / {item.max_change_paise}</td><td>{item.gain_count}</td><td>{item.lose_count}</td></tr>)}</tbody></table></div> : null}
  </main>;
}
