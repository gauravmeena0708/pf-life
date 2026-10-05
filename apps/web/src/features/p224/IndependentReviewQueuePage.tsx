import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import en from "../../i18n/p224-grievance-service.en.json";
import hi from "../../i18n/p224-grievance-service.hi.json";

interface Review { grievance_id: string; state: string; original_resolution: string; reason: string; request_deadline: string; decision_due_at: string; subject: string; office_id: string }

/** Zonal independent review queue; API confines results to other offices in the reviewer zone. */
export function IndependentReviewQueuePage() {
  const { i18n } = useTranslation();
  const words = (i18n.language ?? "en").startsWith("hi") ? hi : en;
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const query = useQuery({ queryKey: ["p224-review-queue"], retry: false,
    queryFn: () => api<Envelope<Review[]>>("/api/v1/office/grievance-reviews") });
  const dt = (value: string) => new Intl.DateTimeFormat(i18n.language ?? "en", { dateStyle: "long", timeStyle: "short" }).format(new Date(value));

  async function decide(event: FormEvent<HTMLFormElement>, grievanceId: string) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    setError(null); setNotice("");
    try {
      await command("POST", `/api/v1/office/grievance-reviews/${grievanceId}/decision`, {
        outcome: data.get("outcome"), reasons: data.get("reasons"),
      });
      setNotice(words.submitted); await qc.invalidateQueries({ queryKey: ["p224-review-queue"] });
    } catch (cause) { setError(cause); }
  }

  return <main className="stack" aria-labelledby="p224-queue-heading">
    <PageHeader id="p224-queue-heading" eyebrow="P2.24" title={words.queueHeading} description={words.queueIntro} current={words.queueHeading} />
    <ProblemMessage error={query.error ?? error} />
    {notice ? <p role="status" aria-live="polite">{notice}</p> : null}
    {!query.data?.data.length ? <p className="card" aria-live="polite">{words.empty}</p> : null}
    {query.data?.data.map((review) => <section className="card stack" key={review.grievance_id}>
      <h2>{words.grievance} <code>{review.grievance_id}</code> · {review.subject}</h2>
      <dl className="kv"><dt>{words.office}</dt><dd>{review.office_id}</dd><dt>{words.requestDeadline}</dt><dd>{dt(review.request_deadline)}</dd><dt>{words.decisionDeadline}</dt><dd>{dt(review.decision_due_at)}</dd></dl>
      <p><strong>{words.reason}:</strong> {review.reason}</p><p><strong>{words.outcome}:</strong> {review.original_resolution}</p>
      <form className="stack" onSubmit={(event) => void decide(event, review.grievance_id)}>
        <label htmlFor={`p224-outcome-${review.grievance_id}`}>{words.outcome}</label>
        <select id={`p224-outcome-${review.grievance_id}`} name="outcome" required defaultValue="UPHELD"><option value="UPHELD">{words.upholdOption}</option><option value="FRESH_DECISION">{words.freshOption}</option></select>
        <label htmlFor={`p224-reasons-${review.grievance_id}`}>{words.reasons}</label>
        <textarea id={`p224-reasons-${review.grievance_id}`} name="reasons" required minLength={10} maxLength={4000} />
        <button className="primary" type="submit">{words.decide}</button>
      </form>
    </section>)}
  </main>;
}
