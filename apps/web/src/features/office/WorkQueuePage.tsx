import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime, roleLabel } from "../journeyB";
import type { OfficeCase } from "./types";

interface Queue { office_id: string; role: string; items: OfficeCase[] }
export function WorkQueuePage() {
  const { t, i18n } = useTranslation();
  const queue = useQuery({ queryKey: ["office-work-queue"], queryFn: () => api<Envelope<Queue>>("/api/v1/office/work-queue"), retry: false, refetchInterval: 5000 });
  const data = queue.data?.data;
  return <section className="stack" aria-labelledby="work-queue-heading">
    <PageHeader id="work-queue-heading" eyebrow={t("office.eyebrow")} title={t("office.queueTitle")}
      description={data ? `${data.office_id} · ${roleLabel(data.role, t)}` : t("office.queueDescription")} current={t("navigation.workQueue")} />
    <section className="card stack" aria-labelledby="queue-cases-heading"><h2 id="queue-cases-heading">{t("office.cases")}</h2><ProblemMessage error={queue.error} />
      {queue.isLoading ? <p role="status">{t("office.loadingQueue")}</p> : null}
      {data?.items.length === 0 ? <p className="empty-state">{t("office.emptyQueue")}</p> : null}
      {data?.items.length ? <div className="table-scroll"><table><thead><tr><th scope="col">{t("office.caseId")}</th><th scope="col">{t("claims.claimId")}</th><th scope="col">{t("claims.form")}</th><th scope="col" className="numeric">{t("claims.amount")}</th><th scope="col">{t("office.chainProgress")}</th><th scope="col">{t("office.slaDue")}</th><th scope="col">{t("office.nextAction")}</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.case_id}>
        <td><Link to={item.grievance_id ? `/office/grievances/${item.grievance_id}` : `/office/cases/${item.case_id}`}><code>{item.case_id}</code></Link></td>
        <td><code>{item.claim_id ?? item.grievance_id}</code>{item.advisory_signal_id ? <><br /><span className="state-pill" title={t("office.advisoryHelp")}>{t("office.advisory")}</span></> : null}</td>
        <td>{item.grievance_id ? t("office.grievanceKind") : item.form_type}</td><td className="numeric">{item.grievance_id ? "—" : rupees(item.amount_paise)}</td>
        <td>{item.chain.length ? t("office.stepOf", { step: Math.min(item.step + 1, item.chain.length), total: item.chain.length }) : "—"}</td><td>{dateTime(item.sla_due_at, i18n.language)}</td><td>{item.next_action ? <span className="state-pill">{t(`office.actions.${item.next_action}`)}</span> : "—"}</td>
      </tr>)}</tbody></table></div> : null}
    </section>
  </section>;
}
