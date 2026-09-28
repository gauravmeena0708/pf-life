import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateOnly, dateTime, stateLabel } from "../journeyB";
import { CorrectionForm } from "./CorrectionForm";
import { PensionEstimate } from "./PensionEstimate";

interface Member { member_id: string; uan: string; name: string; date_of_birth: string; gender: string; mobile_masked: string; email_masked: string; bank: { ifsc: string; account_last4: string }; kyc: { aadhaar: string; pan: string; bank: string }; account_link_ids: string[] }
interface Assurance { kyc: Member["kyc"]; level: "FULL" | "PARTIAL"; next_step: string }
interface Employment { account_link_id: string; establishment_name: string; date_of_joining: string; date_of_exit: string | null; status: string }
interface Notice { id: string; template: string; reference_id: string; title: string; body: string; created_at: string; read_at: string | null }

export function ProfilePage() {
  const { t, i18n } = useTranslation();
  const profile = useQuery({ queryKey: ["member-profile"], queryFn: () => api<Envelope<Member>>("/api/v1/members/me"), retry: false });
  const assurance = useQuery({ queryKey: ["member-assurance"], queryFn: () => api<Envelope<Assurance>>("/api/v1/members/me/identity-assurance"), retry: false });
  const history = useQuery({ queryKey: ["member-employment"], queryFn: () => api<Envelope<Employment[]>>("/api/v1/members/me/employment-history"), retry: false });
  const notices = useQuery({ queryKey: ["member-notifications"], queryFn: () => api<Envelope<Notice[]>>("/api/v1/members/me/notifications"), retry: false, refetchInterval: 5000 });
  const member = profile.data?.data;
  return <section className="stack" aria-labelledby="profile-heading"><PageHeader id="profile-heading" eyebrow={t("profile.eyebrow")} title={t("profile.title")} description={t("profile.description")} current={t("navigation.profile")} />
    <section className="card stack" aria-labelledby="member-profile-heading"><h2 id="member-profile-heading">{t("profile.memberDetails")}</h2><ProblemMessage error={profile.error} />
      {profile.isLoading ? <p role="status">{t("profile.loading")}</p> : null}
      {member ? <dl className="profile-grid">
        <div><dt>{t("profile.name")}</dt><dd>{member.name}</dd></div><div><dt>{t("profile.uan")}</dt><dd><code>{member.uan}</code></dd></div>
        <div><dt>{t("profile.dob")}</dt><dd>{dateOnly(member.date_of_birth, i18n.language)}</dd></div><div><dt>{t("profile.gender")}</dt><dd>{member.gender}</dd></div>
        <div><dt>{t("profile.mobile")}</dt><dd>{member.mobile_masked}</dd></div><div><dt>{t("profile.email")}</dt><dd>{member.email_masked}</dd></div>
        <div><dt>{t("profile.ifsc")}</dt><dd><code>{member.bank.ifsc}</code></dd></div><div><dt>{t("profile.bankEnding")}</dt><dd>•••• {member.bank.account_last4}</dd></div>
      </dl> : null}</section>
    <section className="card stack" aria-labelledby="assurance-heading"><div className="section-heading"><h2 id="assurance-heading">{t("profile.identity")}</h2>{assurance.data ? <span className="state-pill">{stateLabel(assurance.data.data.level, t)}</span> : null}</div>
      <ProblemMessage error={assurance.error} />{assurance.isLoading ? <p role="status">{t("profile.loadingIdentity")}</p> : null}
      {assurance.data ? <><dl className="kv"><dt>{t("profile.aadhaar")}</dt><dd>{assurance.data.data.kyc.aadhaar}</dd><dt>{t("profile.pan")}</dt><dd>{assurance.data.data.kyc.pan}</dd><dt>{t("profile.bankKyc")}</dt><dd>{assurance.data.data.kyc.bank}</dd></dl><p className="pending-notice">{assurance.data.data.next_step}</p></> : null}</section>
    <section className="card stack" aria-labelledby="employment-heading"><h2 id="employment-heading">{t("profile.employment")}</h2><ProblemMessage error={history.error} />
      {history.isLoading ? <p role="status">{t("profile.loadingEmployment")}</p> : null}
      {history.data?.data.length === 0 ? <p className="muted">{t("profile.noEmployment")}</p> : null}
      {history.data?.data.length ? <div className="table-scroll"><table><thead><tr><th scope="col">{t("claims.account")}</th><th scope="col">{t("profile.establishment")}</th><th scope="col">{t("profile.joined")}</th><th scope="col">{t("profile.exited")}</th><th scope="col">{t("claims.status")}</th></tr></thead><tbody>{history.data.data.map((row) => <tr key={row.account_link_id}><td><code>{row.account_link_id}</code></td><td>{row.establishment_name}</td><td>{dateOnly(row.date_of_joining, i18n.language)}</td><td>{dateOnly(row.date_of_exit, i18n.language)}</td><td><span className="state-pill">{stateLabel(row.status, t)}</span></td></tr>)}</tbody></table></div> : null}</section>
    <section className="card stack" aria-labelledby="notices-heading"><h2 id="notices-heading">{t("profile.notices")}</h2><ProblemMessage error={notices.error} />
      {notices.isLoading ? <p role="status">{t("profile.loadingNotices")}</p> : null}
      {notices.data?.data.length === 0 ? <p className="muted">{t("profile.noNotices")}</p> : null}
      {notices.data?.data.length ? <ol className="notice-list">{[...notices.data.data].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).map((notice) => <li key={notice.id}><h3>{notice.title}</h3><p>{notice.body}</p><time dateTime={notice.created_at} className="muted small">{dateTime(notice.created_at, i18n.language)}</time></li>)}</ol> : null}
    {member ? <CorrectionForm uan={member.uan} onDone={() => void profile.refetch()} /> : null}
    <PensionEstimate />
    </section>
  </section>;
}
