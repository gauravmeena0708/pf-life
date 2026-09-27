import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { dateTime, stateLabel } from "../journeyB";
import { GrievanceThread } from "./GrievanceThread";
import type { Grievance } from "./types";

/** A member's grievance: the conversation, replies, escalation to the next tier and reopening (Journey C). */
export function GrievanceDetailPage() {
  const { t, i18n } = useTranslation();
  const { grievanceId } = useParams();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const detail = useQuery({
    queryKey: ["grievance", grievanceId], enabled: !!grievanceId, retry: false,
    queryFn: () => api<Envelope<Grievance>>(`/api/v1/grievances/${grievanceId}`),
    refetchInterval: (q) => q.state.data && q.state.data.data.state !== "CLOSED" ? 5000 : false,
  });
  const g = detail.data?.data;

  async function act(path: string, body: unknown, ok: string, form?: HTMLFormElement) {
    setBusy(true); setError(null); setNotice(null);
    try {
      await command("POST", `/api/v1/grievances/${grievanceId}/${path}`, body);
      form?.reset();
      setNotice(ok);
      await qc.invalidateQueries({ queryKey: ["grievance", grievanceId] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  const text = (e: FormEvent<HTMLFormElement>, name: string) => String(new FormData(e.currentTarget).get(name)).trim();

  return (
    <section className="stack" aria-labelledby="grievance-heading">
      <PageHeader id="grievance-heading" eyebrow={t("grievances.eyebrow")} title={g ? g.subject : t("grievances.title")}
        description={g ? `${g.grievance_id} · ${t(`grievances.categories.${g.category}`)}` : ""}
        current={g?.grievance_id ?? ""} parent={{ label: t("navigation.grievances"), to: "/member/grievances" }}>
        {g ? <span className="state-pill">{stateLabel(g.state, t)}</span> : null}
      </PageHeader>
      <ProblemMessage error={detail.error} />
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      {g ? (
        <>
          <aside className="pending-notice" aria-label={t("claims.nextStep")}>
            <h2>{t("grievances.whereItIs")}</h2>
            <p>{g.resolved_at ? t("grievances.resolvedBy", { tier: t(`grievances.tiers.${g.tier}`), when: dateTime(g.resolved_at, i18n.language) })
              : t("grievances.withTier", { tier: t(`grievances.tiers.${g.tier}`), due: dateTime(g.sla_due_at, i18n.language) })}</p>
            {g.resolution ? <p><strong>{t("grievances.resolution")}:</strong> {g.resolution}</p> : null}
          </aside>
          <section className="card stack" aria-labelledby="g-summary"><h2 id="g-summary">{t("grievances.details")}</h2>
            <p>{g.description}</p>
            {g.linked_claim_id ? <p className="small">{t("grievances.linkedClaim")}: <code>{g.linked_claim_id}</code></p> : null}
          </section>
          <GrievanceThread grievance={g} viewer="member" />
          {g.state !== "CLOSED" && g.state !== "RESOLVED" ? (
            <div className="activity-columns">
              <form className="card stack" onSubmit={(e) => { e.preventDefault(); void act("messages", { body: text(e, "body") }, t("grievances.sent"), e.currentTarget); }}>
                <h2>{t("grievances.addMessage")}</h2>
                <label>{t("grievances.message")}<textarea name="body" required minLength={2} maxLength={4000} /></label>
                <div className="actions"><button type="submit" className="primary" disabled={busy}>{t("grievances.send")}</button></div>
              </form>
              {g.state !== "ESCALATED" && g.tier !== "HO" ? (
                <form className="card stack" onSubmit={(e) => { e.preventDefault(); void act("escalations", { reason: text(e, "reason") }, t("grievances.escalated"), e.currentTarget); }}>
                  <h2>{t("grievances.escalate")}</h2>
                  <p className="muted small">{t("grievances.escalateHelp")}</p>
                  <label>{t("grievances.reason")}<textarea name="reason" required minLength={5} maxLength={1000} /></label>
                  <div className="actions"><button type="submit" disabled={busy}>{t("grievances.escalateButton")}</button></div>
                </form>
              ) : null}
            </div>
          ) : null}
          {g.state === "RESOLVED" ? (
            <form className="card stack" onSubmit={(e) => { e.preventDefault(); void act("reopen-requests", { reason: text(e, "reason") }, t("grievances.reopened"), e.currentTarget); }}>
              <h2>{t("grievances.reopen")}</h2>
              <p className="muted small">{t("grievances.reopenHelp")}</p>
              <label>{t("grievances.reason")}<textarea name="reason" required minLength={5} maxLength={1000} /></label>
              <div className="actions"><button type="submit" disabled={busy}>{t("grievances.reopenButton")}</button></div>
            </form>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
