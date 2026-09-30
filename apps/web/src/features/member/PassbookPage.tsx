import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api, rupees, type Envelope } from "../../api/client";
import { AnnualStatement } from "./AnnualStatement";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";

interface PassbookEntry {
  wage_month: string;
  employee_share_paise: number;
  employer_share_paise: number;
  establishment_name: string;
  trrn: string;
  posted_at: string;
  running_balance_paise: number;
}
interface Passbook {
  accounts: { account_link_id: string; entries: PassbookEntry[] }[];
  pending: { account_link_id: string; wage_month: string; trrn: string | null; status: string; message: string }[];
}

export function PassbookPage() {
  const { t } = useTranslation();
  const passbook = useQuery({
    queryKey: ["member-passbook"],
    queryFn: () => api<Envelope<Passbook>>("/api/v1/members/me/passbook"),
    retry: false,
    refetchInterval: (query) => (query.state.data?.data.pending.length ?? 0) > 0 ? 5_000 : false,
  });
  const accounts = passbook.data?.data.accounts ?? [];
  const pending = passbook.data?.data.pending ?? [];
  const entries = accounts.flatMap((account) => account.entries);
  const totalBalance = accounts.reduce((total, account) => total + (account.entries.at(-1)?.running_balance_paise ?? 0), 0);
  const lastMonth = entries.reduce<string>((latest, entry) => entry.wage_month > latest ? entry.wage_month : latest, "");

  return <div className="stack passbook-page">
    <PageHeader eyebrow={t("passbook.eyebrow")} title={t("passbook.title")} description={t("passbook.description")} current={t("passbook.title")} />
    <ProblemMessage error={passbook.error} />
    {passbook.isLoading ? <p role="status">{t("passbook.loading")}</p> : null}
    {passbook.data ? <>
      <section className="metrics passbook-metrics" aria-label={t("passbook.summary")}>
        <div><span>{t("passbook.totalBalance")}</span><strong>{rupees(totalBalance)}</strong></div>
        <div><span>{t("passbook.contributions")}</span><strong>{entries.length}</strong></div>
        <div><span>{t("passbook.lastMonth")}</span><strong>{lastMonth || "—"}</strong></div>
      </section>
      {pending.length > 0 ? <section className="pending-notice" aria-labelledby="pending-heading">
        <h2 id="pending-heading">{t("passbook.pendingTitle")}</h2>
        <p>{t("passbook.pendingDescription")}</p>
        <ul>{pending.map((item, index) => <li key={`${item.account_link_id}-${item.wage_month}-${item.trrn ?? index}`}>
          <strong>{item.wage_month}</strong> · {item.account_link_id} · {item.status}{item.trrn ? ` · ${item.trrn}` : ""}<br />{item.message}
        </li>)}</ul>
      </section> : null}
      {entries.length === 0 ? <div className="card empty-state"><h2>{t("passbook.empty")}</h2><p>{t("passbook.emptyDescription")}</p></div> : null}
      {accounts.filter((account) => account.entries.length > 0).map((account) => <section key={account.account_link_id} className="card stack" aria-labelledby={`account-${account.account_link_id}`}>
        <div className="section-heading"><div><p className="eyebrow">{t("passbook.account")}</p><h2 id={`account-${account.account_link_id}`}>{account.account_link_id}</h2></div></div>
        <div className="table-scroll"><table className="passbook-table">
          <thead><tr><th scope="col">{t("passbook.wageMonth")}</th><th scope="col">{t("passbook.establishment")}</th><th scope="col" className="numeric">{t("passbook.employeeShare")}</th><th scope="col" className="numeric">{t("passbook.employerShare")}</th><th scope="col" className="numeric">{t("passbook.runningBalance")}</th><th scope="col">{t("passbook.trrn")}</th></tr></thead>
          <tbody>{account.entries.map((entry, index) => <tr key={`${entry.trrn}-${entry.wage_month}-${index}`}>
            <td>{entry.wage_month}</td><td>{entry.establishment_name}</td><td className="numeric">{rupees(entry.employee_share_paise)}</td><td className="numeric">{rupees(entry.employer_share_paise)}</td><td className="numeric"><strong>{rupees(entry.running_balance_paise)}</strong></td><td><code>{entry.trrn}</code></td>
          </tr>)}</tbody>
        </table></div>
    </section>)}
    <AnnualStatement />
    </> : null}
  </div>;
}
