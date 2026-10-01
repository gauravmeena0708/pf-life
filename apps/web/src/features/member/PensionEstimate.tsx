import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api, rupees, type Envelope } from "../../api/client";

interface Scenario { label: string; service_months: number; eligible: boolean; monthly_paise: number; working?: string; reason?: string }
interface Spell { account_link_id: string; establishment_id?: string | null; from: string; to: string | null; months: number; breaks_months: number }
interface Estimate { rule_version: string; age_years: number; service_months_so_far: number; service_by_member_id?: Spell[]; pensionable_salary_paise: number; min_service_years: number; scenarios: Scenario[]; note: string }

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
      {e.service_by_member_id && e.service_by_member_id.length > 1 ? <div className="table-scroll"><table aria-label={t("pensionService.byMemberId")}>
        <thead><tr><th scope="col">{t("pensionService.memberId")}</th><th scope="col">{t("pensionService.period")}</th><th scope="col">{t("pensionService.months")}</th></tr></thead>
        <tbody>{e.service_by_member_id.map((x) => <tr key={x.account_link_id}><td><code>{x.account_link_id}</code></td>
          <td>{x.from} – {x.to ?? t("pensionService.inService")}</td><td>{x.months}{x.breaks_months ? ` (−${x.breaks_months})` : ""}</td></tr>)}</tbody>
      </table></div> : null}
      <p className="muted small">{e.note} ({e.rule_version})</p>
    </section>
  );
}
