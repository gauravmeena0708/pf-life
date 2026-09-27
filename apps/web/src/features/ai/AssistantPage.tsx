import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { command, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { FeedbackButtons } from "./FeedbackButtons";

export interface KnowledgeAnswer {
  answer: string; citations: { ref: string; title: string; excerpt: string; verified: boolean }[]; uncertainty: string;
  mode: "llm" | "extractive" | "refused"; model_id: string; advisory_only: boolean; ignored_instructions: string[];
  interaction_id: string;
}

const EXAMPLES = ["assistant.example1", "assistant.example2", "assistant.example3"];

/** Member assistant (Journey E2): answers from approved documents, with sources and stated uncertainty. */
export function AssistantPage() {
  const { t } = useTranslation();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function ask(e?: FormEvent<HTMLFormElement>, text = question) {
    e?.preventDefault();
    if (text.trim().length < 3) return;
    setBusy(true); setError(null);
    try {
      setAnswer((await command<Envelope<KnowledgeAnswer>>("POST", "/api/v1/ai/knowledge/search", { question: text.trim() })).data);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return (
    <section className="stack" aria-labelledby="assistant-heading">
      <PageHeader id="assistant-heading" eyebrow={t("assistant.eyebrow")} title={t("assistant.title")}
        description={t("assistant.description")} current={t("navigation.assistant")} />
      <form className="card stack" onSubmit={(e) => void ask(e)}>
        <label htmlFor="assistant-q">{t("assistant.question")}</label>
        <div className="search-input-row">
          <input id="assistant-q" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={500} required minLength={3} />
          <button type="submit" className="primary" disabled={busy}>{t("assistant.ask")}</button>
        </div>
        <div className="mode-options">
          {EXAMPLES.map((key) => (
            <button type="button" key={key} className="mode-option" onClick={() => { setQuestion(t(key)); void ask(undefined, t(key)); }}>{t(key)}</button>
          ))}
        </div>
        <p className="demo-tip">{t("assistant.notice")}</p>
      </form>
      <ProblemMessage error={error} />
      {answer ? (
        <article className="card stack" aria-live="polite" aria-labelledby="answer-heading">
          <div className="section-heading">
            <h2 id="answer-heading">{t("assistant.answer")}</h2>
            <span className="state-pill">{t(`assistant.modes.${answer.mode}`)}</span>
          </div>
          <p>{answer.answer}</p>
          <p className="muted small"><strong>{t("assistant.uncertainty")}:</strong> {answer.uncertainty}</p>
          {answer.citations.length ? (
            <div className="stack">
              <h3>{t("assistant.sources")}</h3>
              <ul className="lookup-results">
                {answer.citations.map((c) => <li key={c.ref}><strong>{c.ref} · {c.title}{c.verified ? "" : ` (${t("assistant.unverified")})`}</strong><span>{c.excerpt}</span></li>)}
              </ul>
            </div>
          ) : null}
          {answer.ignored_instructions.length ? (
            <p className="demo-tip"><strong>{t("assistant.ignoredTitle")}</strong> {t("assistant.ignored", { refs: answer.ignored_instructions.join(", ") })}</p>
          ) : null}
          <FeedbackButtons interactionId={answer.interaction_id} />
          <p className="muted small">{t("assistant.model", { model: answer.model_id })}</p>
        </article>
      ) : null}
    </section>
  );
}
