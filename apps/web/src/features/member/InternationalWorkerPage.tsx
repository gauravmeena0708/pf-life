import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, api, getSession, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import type { Agreement } from "../international/types";

interface InternationalWorker {
  uan: string; name: string; international_worker: boolean; nationality: string | null; passport_masked: string | null;
  employment: { account_link_id: string; establishment: string; date_of_joining: string; date_of_exit: string | null }[];
  agreement: Agreement | null; coverage: string;
}

export function InternationalWorkerPage() {
  const { t } = useTranslation();
  const session = useQuery({ queryKey: ["session"], queryFn: getSession, retry: false });
  const allowed = session.data?.stakeholder === "member";
  const worker = useQuery({ queryKey: ["international-worker"], enabled: allowed, retry: false,
    queryFn: () => api<Envelope<InternationalWorker>>("/api/v1/members/me/international") });
  const data = worker.data?.data;
  const notRecorded = worker.error instanceof ApiError && worker.error.problem.status === 404;
  return <section className="stack" aria-labelledby="intl-worker-heading">
    <PageHeader id="intl-worker-heading" eyebrow={t("memberHome.eyebrow")} title={t("iw.title")}
      description={t("iw.description")} current={t("iw.current")} />
    <ProblemMessage error={session.error ?? (notRecorded ? null : worker.error)} />
    {session.isLoading || worker.isLoading ? <p role="status">{t("iw.loading")}</p> : null}
    {session.data && (!allowed || notRecorded) ? <p className="pending-notice">{t("iw.unavailable")}</p> : null}
    {allowed && data ? <><section className="card stack"><h2>{t("iw.details")}</h2>
      <dl className="kv"><dt>{t("iw.name")}</dt><dd>{data.name}</dd><dt>{t("memberHome.uan")}</dt><dd>{data.uan}</dd>
        <dt>{t("iw.worker")}</dt><dd>{t(data.international_worker ? "iw.yes" : "iw.no")}</dd><dt>{t("iw.nationality")}</dt><dd>{data.nationality ?? "—"}</dd>
        <dt>{t("iw.passport")}</dt><dd>{data.passport_masked ?? "—"}</dd></dl><p className="pending-notice">{data.coverage}</p>
      <h3>{t("iw.agreement")}</h3>{data.agreement ? <><p>{data.agreement.country} · {data.agreement.code} · {t("iw.inForce")} {data.agreement.in_force_from}</p>
        <p>{t("iw.maximumPosting")} {data.agreement.max_posting_months} {t("iw.months")} · {t("iw.maximumExtension")} {data.agreement.max_extension_months} {t("iw.months")} · {t("iw.totalisation")} {t(data.agreement.totalisation ? "iw.yes" : "iw.no")}</p>
        <p>{data.agreement.note}</p></> : <p>{t("iw.noAgreement")}</p>}
    </section><section className="card stack"><h2>{t("iw.employment")}</h2>
      {data.employment.length ? <div className="table-scroll"><table><thead><tr><th scope="col">{t("iw.memberId")}</th><th scope="col">{t("iw.establishment")}</th>
        <th scope="col">{t("iw.joining")}</th><th scope="col">{t("iw.exit")}</th></tr></thead><tbody>{data.employment.map((item) => <tr key={item.account_link_id}>
          <th scope="row">{item.account_link_id}</th><td>{item.establishment}</td><td>{item.date_of_joining}</td><td>{item.date_of_exit ?? t("iw.inService")}</td>
        </tr>)}</tbody></table></div> : <p className="muted">{t("iw.noEmployment")}</p>}
    </section></> : null}
  </section>;
}
