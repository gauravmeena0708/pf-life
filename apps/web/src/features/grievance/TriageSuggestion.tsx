import { useEffect, useState } from "react";

import { command, type Envelope } from "../../api/client";
import { FeedbackButtons } from "../ai/FeedbackButtons";

interface Suggestion { suggested_category: string; matched_terms: string[]; confidence: string; note: string; interaction_id: string }

/** Advisory category suggestion for the PRO (Journey E, grievance triage). The category is never changed automatically. */
export function TriageSuggestion({ text, current }: { text: string; current: string }) {
  const [s, setS] = useState<Suggestion | null>(null);
  useEffect(() => {
    command<Envelope<Suggestion>>("POST", "/api/v1/ai/grievances/classify", { text }).then((r) => setS(r.data)).catch(() => setS(null));
  }, [text]);
  if (!s) return null;
  return (
    <aside className="demo-tip stack" aria-label="Triage suggestion">
      <p><strong>Triage suggestion (advisory):</strong> {s.suggested_category.replaceAll("_", " ").toLowerCase()}
        {s.suggested_category === current ? " — matches the member's choice." : ` — the member chose ${current.replaceAll("_", " ").toLowerCase()}.`}
        {s.matched_terms.length ? ` Matched: ${s.matched_terms.join(", ")}.` : ""} Confidence {s.confidence}.</p>
      <FeedbackButtons interactionId={s.interaction_id} />
    </aside>
  );
}
