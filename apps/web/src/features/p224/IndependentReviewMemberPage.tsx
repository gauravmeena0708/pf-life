import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import en from "../../i18n/p224-grievance-service.en.json";
import hi from "../../i18n/p224-grievance-service.hi.json";

interface Review { grievance_id: string; state: string; reason?: string; outcome?: string; reasons?: string; request_deadline?: string | null; decision_due_at?: string | null }
interface GrievanceSummary { subject: string; resolution: string | null; state: string }

/** Member request and outcome view for the P2.24 independent review. */
export function IndependentReviewMemberPage() {
  const { grievanceId = "" } = useParams();
  const { i18n } = useTranslation();
  const words = (i18n.language ?? "en").startsWith("hi") ? hi : en;
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const query = useQuery({ queryKey: ["p224-member-review", grievanceId], enabled: !!grievanceId, retry: false,
    queryFn: () => api<Envelope<Review>>(`/api/v1/members/me/grievances/${grievanceId}/review`) });
  const grievance = useQuery({ queryKey: ["p224-grievance", grievanceId], enabled: !!grievanceId, retry: false,
    // The member reads their own grievances (the detail route is for the assigned office).
    queryFn: async () => {
      const mine = await api<Envelope<(GrievanceSummary & { grievance_id: string })[]>>("/api/v1/members/me/grievances");
      const own = mine.data.find((g) => g.grievance_id === grievanceId);
      return own ? { ...mine, data: own } : null;
    } });
  const review = query.data?.data;
  const dt = (value?: string | null) => value ? new Intl.DateTimeFormat(i18n.language ?? "en", { dateStyle: "long", timeStyle: "short" }).format(new Date(value)) : "—";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setError(null); setNotice("");
    try {
      await command("POST", `/api/v1/members/me/grievances/${grievanceId}/reviews`, { reason: new FormData(form).get("reason") });
      form.reset(); setNotice(words.pending);
      await qc.invalidateQueries({ queryKey: ["p224-member-review", grievanceId] });
    } catch (cause) { setError(cause); }
  }

  return <main className="stack" aria-labelledby="p224-review-heading">
    <PageHeader id="p224-review-heading" eyebrow="P2.24" title={words.heading} description={words.memberIntro} current={words.heading} />
    <ProblemMessage error={query.error ?? error} />
    {review ? <section className="card stack" aria-live="polite">
      {grievance.data ? <><h2>{grievance.data.data.subject}</h2><p><strong>{words.originalResolution}:</strong> {grievance.data.data.resolution ?? "—"}</p></> : null}
      {review.state === "NOT_REQUESTED" && review.request_deadline ? <>
        <p>{words.memberIntro}</p><p><strong>{words.requestDeadline}:</strong> {dt(review.request_deadline)}</p>
        <form className="stack" onSubmit={(event) => void submit(event)}>
          <label htmlFor="p224-review-reason">{words.reason}</label>
          <textarea id="p224-review-reason" name="reason" required minLength={10} maxLength={2000} />
          <button className="primary" type="submit">{words.request}</button>
        </form>
      </> : null}
      {review.state === "NOT_REQUESTED" && !review.request_deadline ? <p>{words.closedOnly}</p> : null}
      {review.state === "PENDING" ? <><p>{words.pending}</p><p><strong>{words.requestDeadline}:</strong> {dt(review.request_deadline)}</p><p><strong>{words.decisionDeadline}:</strong> {dt(review.decision_due_at)}</p></> : null}
      {review.state === "DECIDED" ? <><h2>{words.outcome}: {review.outcome === "UPHELD" ? words.upheld : words.fresh}</h2><p><strong>{words.reasons}:</strong> {review.reasons}</p><p><strong>{words.decisionDeadline}:</strong> {dt(review.decision_due_at)}</p></> : null}
      {notice ? <p role="status">{notice}</p> : null}
    </section> : null}
  </main>;
}
