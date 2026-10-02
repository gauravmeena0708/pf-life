import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import "./Messages.css";

interface Preferences { sms: boolean; email: boolean; language: "en" | "hi"; essential_sms_titles: string[]; essential_sms_notice: string }

export function MessagePreferences() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const preferences = useQuery({ queryKey: ["notification-preferences"], queryFn: () => api<Envelope<Preferences>>("/api/v1/members/me/notification-preferences"), retry: false });
  const [form, setForm] = useState<Pick<Preferences, "sms" | "email" | "language"> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (preferences.data) { const { sms, email, language } = preferences.data.data; setForm({ sms, email, language }); } }, [preferences.data]);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!form) return;
    setBusy(true); setError(null); setSaved(false);
    try {
      const result = await command<Envelope<Preferences>>("PUT", "/api/v1/members/me/notification-preferences", form);
      qc.setQueryData(["notification-preferences"], result);
      setSaved(true);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <form className="card stack" aria-labelledby="messages-heading" onSubmit={(e) => void save(e)}>
    <h2 id="messages-heading">{t("messages.heading")}</h2>
    <ProblemMessage error={preferences.error ?? error} />
    {preferences.isLoading ? <p role="status">{t("messages.loading")}</p> : null}
    {form ? <><div className="message-options">
      <label><input type="checkbox" checked={form.sms} onChange={(e) => setForm({ ...form, sms: e.target.checked })} /> {t("messages.sms")}</label>
      <label><input type="checkbox" checked={form.email} onChange={(e) => setForm({ ...form, email: e.target.checked })} /> {t("messages.email")}</label>
      <label>{t("messages.language")}<select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value as "en" | "hi" })}><option value="en">English</option><option value="hi">हिन्दी</option></select></label>
    </div><p className="muted small">{t("messages.essential")}</p>
      {preferences.data?.data.essential_sms_titles.length ? <ul className="message-essential">{preferences.data.data.essential_sms_titles.map((title) => <li key={title}>{title}</li>)}</ul> : null}
      <div className="actions"><button type="submit" className="primary" disabled={busy}>{t("messages.save")}</button></div>
      {saved ? <p role="status" className="ok">{t("messages.saved")}</p> : null}</> : null}
  </form>;
}
