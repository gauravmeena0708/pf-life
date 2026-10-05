import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { api, type Envelope } from "../../api/client";
import en from "../../i18n/p224-reporting-service.en.json";
import hi from "../../i18n/p224-reporting-service.hi.json";
import "./serviceStandards.css";

interface Performance { completed: number; within_pct: number; median_days: number; p90_days: number;
  open_past_standard: number | null; met: boolean }
interface Standard { code: string; name: string; days: number; basis: "STATUTORY" | "TARGET";
  availability: string; performance: Performance | null }
interface Report { as_of: string; period_days: number; standards: Standard[];
  offices: { office_id: string; standards: Standard[] }[] }

const names: Record<string, [string, string]> = {
  CLAIM_SETTLEMENT: ["Claim settlement", "दावा निपटान"],
  AUTO_CLAIM: ["Auto-settled claim", "स्वतः निपटाया गया दावा"],
  GRIEVANCE: ["Grievance resolution", "शिकायत निवारण"],
  TRANSFER: ["PF transfer", "भविष्य निधि स्थानांतरण"],
};

export function ServiceStandardsPage() {
  const { i18n } = useTranslation();
  const words = i18n.language.startsWith("hi") ? hi : en;
  const hindi = i18n.language.startsWith("hi");
  const [days, setDays] = useState(30);
  const report = useQuery({ queryKey: ["public-service-standards", days], retry: false,
    queryFn: () => api<Envelope<Report>>(`/api/v1/public/service-standards?days=${days}`) });
  const data = report.data?.data;
  const label = (standard: Standard) => names[standard.code]?.[hindi ? 1 : 0] ?? standard.name;
  return <main className="p224-standards" aria-labelledby="p224-title">
    <header className="p224-heading"><p>{words.demo}</p><h1 id="p224-title">{words.title}</h1><p>{words.intro}</p></header>
    <div className="p224-content">
      <label htmlFor="p224-period">{words.period}</label>{" "}
      <select id="p224-period" value={days} onChange={(event) => setDays(Number(event.target.value))}>
        <option value={30}>{words.days30}</option><option value={90}>{words.days90}</option>
      </select>
      <div aria-live="polite">
        {report.isLoading ? <p role="status">{words.loading}</p> : null}
        {report.isError ? <p role="alert">{words.error}</p> : null}
        {data ? <>
          <div className="p224-table-wrap"><table><caption>{words.title}</caption><thead><tr>
            <th scope="col">{words.standard}</th><th scope="col">{words.target}</th>
          </tr></thead><tbody>{data.standards.map((standard) => <tr key={standard.code}>
            <th scope="row">{label(standard)}</th><td>{standard.days} {words.days} · {standard.basis === "STATUTORY" ? words.statutory : words.serviceTarget}</td>
          </tr>)}</tbody></table></div>
          {data.offices.length === 0 ? <p>{words.noOffices}</p> : data.offices.map((office) =>
            <section key={office.office_id} aria-labelledby={`p224-${office.office_id}`}>
              <h2 id={`p224-${office.office_id}`}>{words.office}: {office.office_id}</h2>
              <div className="p224-table-wrap"><table><thead><tr><th scope="col">{words.standard}</th>
                <th scope="col">{words.target}</th><th scope="col">{words.actual}</th><th scope="col">{words.result}</th>
              </tr></thead><tbody>{office.standards.map((standard) => <tr key={standard.code}>
                <th scope="row">{label(standard)}</th><td>{standard.days} {words.days}</td>
                <td>{standard.performance ? <>{standard.performance.within_pct}% {words.within} · {words.median} {standard.performance.median_days} {words.days} · {words.p90} {standard.performance.p90_days} {words.days} · {words.open} {standard.performance.open_past_standard ?? words.suppressed}</>
                  : standard.availability === "SUPPRESSED" ? words.suppressed : words.unavailable}</td>
                <td>{standard.performance ? <strong className={standard.performance.met ? "p224-met" : "p224-unmet"}>{standard.performance.met ? words.met : words.notMet}</strong> : "—"}</td>
              </tr>)}</tbody></table></div>
            </section>)}
          <p className="p224-note">{words.note}</p>
        </> : null}
      </div>
    </div>
  </main>;
}
