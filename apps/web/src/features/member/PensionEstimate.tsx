import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api, rupees, type Envelope } from "../../api/client";

interface Scenario { label: string; service_months: number; eligible: boolean; monthly_paise: number; working?: string; reason?: string }
interface Estimate { rule_version: string; age_years: number; service_months_so_far: number; pensionable_salary_paise: number; min_service_years: number; scenarios: Scenario[]; note: string }

/** EPS pension estimate under the formula in force today (pension-service). */
export function PensionEstimate() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["pension-estimate"], retry: false, queryFn: () => api<Envelope<Estimate>>("/api/v1/members/me/pension-eligibility-preview") });
  const e = q.data?.data;
  if (!e) return null;
  return (
    <section className="card stack" aria-labelledby="pension-estimate-heading"><h2 id="pension-estimate-heading">{t("pensionEstimate.title")}</h2>
      <p className="muted small">{t("pensionEstimate.help", { years: Math.floor(e.service_months_so_far / 12), months: e.service_months_so_far % 12, salary: rupees(e.pensionable_salary_paise), min: e.min_service_years })}</p>
      <div className="table-scroll"><table>
        <thead><tr><th scope="col">{t("pensionEstimate.scenario")}</th><th scope="col">{t("pensionEstimate.service")}</th><th scope="col">{t("pensionEstimate.monthly")}</th></tr></thead>
        <tbody>{e.scenarios.map((s) => <tr key={s.label}><td>{s.label}</td><td>{Math.floor(s.service_months / 12)} {t("pensionEstimate.years")}</td>
          <td>{s.eligible ? <><strong>{rupees(s.monthly_paise)}</strong><br /><span className="muted small">{s.working}</span></> : <span className="muted">{s.reason}</span>}</td></tr>)}</tbody>
      </table></div>
      <p className="muted small">{e.note} ({e.rule_version})</p>
    </section>
  );
}
