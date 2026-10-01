import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { PrivacyRequests } from "./PrivacyRequests";
import { dateTime } from "../journeyB";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

interface Me { member_id: string; uan: string; mobile_masked: string; email_masked: string }
interface SessionRow { session_id: string; created_at: number; last_seen: number; device: string; current: boolean }

/** Member security self-service (Journey D): contact details, sessions, "not me" reports, account recovery. */
export function SecurityPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activatedAt, setActivatedAt] = useState<string | null>(null);
  const me = useQuery({ queryKey: ["member-profile"], queryFn: () => api<Envelope<Me>>("/api/v1/members/me"), retry: false });
  const sessions = useQuery({ queryKey: ["member-sessions"], queryFn: () => api<Envelope<SessionRow[]>>("/api/v1/members/me/sessions"), retry: false });
  const memberId = me.data?.data.member_id ?? "";
  const when = (seconds: number) => dateTime(new Date(seconds * 1000).toISOString(), i18n.language);

  async function run(work: () => Promise<unknown>, ok: string, form?: HTMLFormElement) {
    setBusy(true); setError(null); setNotice(null);
    try {
      await work();
      form?.reset();
      setNotice(ok);
      await qc.invalidateQueries({ queryKey: ["member-profile"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  const field = (e: FormEvent<HTMLFormElement>, name: string) => String(new FormData(e.currentTarget).get(name)).trim();

  async function changeContact(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = { mobile: field(e, "mobile"), email: field(e, "email") };
    const token = await stepUp.ask({ action: "change-contact", resourceId: memberId, summary: t("security.changeSummary") });
    if (!token) return;
    await run(() => command("PATCH", "/api/v1/members/me/contact-details", body, { stepUpToken: token }), t("security.changed"), form);
  }

  async function recover(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const reason = field(e, "reason");
    const token = await stepUp.ask({ action: "request-recovery", resourceId: memberId, summary: t("security.recoverySummary") });
    if (!token) return;
    await run(() => command("POST", "/api/v1/members/me/account-recovery-requests", { reason }, { stepUpToken: token }),
      t("security.recoveryRequested"), form);
  }

  async function activate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy(true); setError(null); setActivatedAt(null);
    try {
      const result = await command<Envelope<{ activated_at: string }>>("POST", "/api/v1/members/uan-activations",
        { uan: me.data?.data.uan, otp: field(e, "otp") });
      setActivatedAt(result.data.activated_at); form.reset();
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return (
    <section className="stack" aria-labelledby="security-heading">
      <PageHeader id="security-heading" eyebrow={t("security.eyebrow")} title={t("security.title")}
        description={t("security.description")} current={t("navigation.accountSecurity")} />
      <ProblemMessage error={me.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      <form className="card stack" aria-labelledby="uan-activation-heading" onSubmit={(e) => void activate(e)}>
        <h2 id="uan-activation-heading">Activate your UAN</h2>
        <label>UAN<input value={me.data?.data.uan ?? ""} readOnly /></label>
        <label>OTP<input name="otp" required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" /></label>
        <p className="muted small">Demo OTP: 123456</p>
        <div className="actions"><button type="submit" className="primary" disabled={busy || !me.data?.data.uan}>Activate UAN</button></div>
        {activatedAt ? <p role="status" className="ok">Activated at {dateTime(activatedAt, i18n.language)}</p> : null}
      </form>
      <div className="activity-columns">
        <form className="card stack" onSubmit={(e) => void changeContact(e)} aria-labelledby="contact-heading">
          <h2 id="contact-heading">{t("security.contact")}</h2>
          {me.data ? <p className="muted">{t("security.currentContact", { mobile: me.data.data.mobile_masked, email: me.data.data.email_masked })}</p> : null}
          <label>{t("security.mobile")}<input name="mobile" required inputMode="numeric" pattern="[6-9][0-9]{9}" maxLength={10} /></label>
          <label>{t("security.email")}<input name="email" type="email" required maxLength={180} /></label>
          <p className="muted small">{t("security.contactHelp")}</p>
          <div className="actions"><button type="submit" className="primary" disabled={busy || !memberId}>{t("security.change")}</button></div>
        </form>
        <section className="card stack" aria-labelledby="sessions-heading">
          <h2 id="sessions-heading">{t("security.sessions")}</h2>
          <ProblemMessage error={sessions.error} />
          <ul className="lookup-results">
            {sessions.data?.data.map((s) => (
              <li key={s.session_id}>
                <strong>{s.current ? t("security.thisSession") : t("security.otherSession")}</strong>
                <span>{t("security.device")} {s.device} · {t("security.signedIn")} {when(s.created_at)} · {t("security.lastSeen")} {when(s.last_seen)}</span>
              </li>
            ))}
          </ul>
          <p className="muted small">{t("security.sessionsHelp")}</p>
        </section>
      </div>
      <div className="activity-columns">
        <form className="card stack" aria-labelledby="report-heading" onSubmit={(e) => {
          e.preventDefault(); const f = e.currentTarget;
          void run(() => command("POST", "/api/v1/members/me/security-reports", { kind: field(e, "kind"), description: field(e, "description") }),
            t("security.reported"), f);
        }}>
          <h2 id="report-heading">{t("security.report")}</h2>
          <label>{t("security.whatHappened")}
            <select name="kind" defaultValue="NOT_ME">
              <option value="NOT_ME">{t("security.kinds.NOT_ME")}</option>
              <option value="SUSPICIOUS_MESSAGE">{t("security.kinds.SUSPICIOUS_MESSAGE")}</option>
              <option value="OTHER">{t("security.kinds.OTHER")}</option>
            </select>
          </label>
          <label>{t("security.details")}<textarea name="description" required minLength={10} maxLength={2000} /></label>
          <div className="actions"><button type="submit" disabled={busy}>{t("security.sendReport")}</button></div>
        </form>
        <form className="card stack" onSubmit={(e) => void recover(e)} aria-labelledby="recovery-heading">
          <h2 id="recovery-heading">{t("security.recovery")}</h2>
          <p className="muted small">{t("security.recoveryHelp")}</p>
          <label>{t("security.reason")}<textarea name="reason" required minLength={10} maxLength={2000} /></label>
          <div className="actions"><button type="submit" className="primary" disabled={busy || !memberId}>{t("security.requestRecovery")}</button></div>
        </form>
      </div>
      <PrivacyRequests />
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
