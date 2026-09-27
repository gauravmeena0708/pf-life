import { useState } from "react";
import { useTranslation } from "react-i18next";

import { command } from "../../api/client";

/** Human feedback on an AI answer (init.md §8.3). Recorded for review; nothing is retrained automatically. */
export function FeedbackButtons({ interactionId }: { interactionId: string }) {
  const { t } = useTranslation();
  const [sent, setSent] = useState<string | null>(null);
  const [correction, setCorrection] = useState("");

  async function send(rating: "helpful" | "not_helpful" | "incorrect") {
    await command("POST", "/api/v1/ai/feedback", { interaction_id: interactionId, rating, correction: correction.trim() || null });
    setSent(rating);
  }

  if (sent) return <p role="status" className="ok">{t("assistant.feedbackThanks")}</p>;
  return (
    <div className="stack">
      <p className="small"><strong>{t("assistant.feedbackQuestion")}</strong></p>
      <div className="actions">
        <button type="button" onClick={() => void send("helpful")}>{t("assistant.helpful")}</button>
        <button type="button" onClick={() => void send("not_helpful")}>{t("assistant.notHelpful")}</button>
        <button type="button" onClick={() => void send("incorrect")}>{t("assistant.incorrect")}</button>
      </div>
      <label className="small">{t("assistant.correction")}<textarea value={correction} onChange={(e) => setCorrection(e.target.value)} maxLength={2000} /></label>
    </div>
  );
}
