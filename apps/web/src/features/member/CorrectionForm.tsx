import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { command } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

const PARAMETERS = ["NAME", "DATE_OF_BIRTH", "GENDER", "FATHER_NAME", "MOTHER_NAME", "MARITAL_STATUS", "NATIONALITY", "DATE_OF_JOINING"];

/** Joint Declaration (profile correction): the member asks; the employer attests; the regional office decides. */
export function CorrectionForm({ uan, onDone }: { uan: string; onDone: () => void }) {
  const { t } = useTranslation();
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const body = Object.fromEntries(["parameter", "current_value", "corrected_value", "reason"].map((k) => [k, String(f.get(k)).trim()]));
    const token = await stepUp.ask({ action: "submit-joint-declaration", resourceId: uan, summary: t("correction.summary") });
    if (!token) return;
    setError(null);
    try {
      const r = await command<{ data: { case_id: string } }>("POST", "/api/v1/members/me/joint-declarations", body, { stepUpToken: token });
      form.reset();
      setNotice(t("correction.sent", { id: r.data.case_id }));
      onDone();
    } catch (cause) { setError(cause); }
  }

  return (
    <form className="card stack" onSubmit={(e) => void submit(e)} aria-labelledby="correction-heading">
      <h2 id="correction-heading">{t("correction.title")}</h2>
      <p className="muted small">{t("correction.help")}</p>
      <ProblemMessage error={error} />
      {notice ? <p role="status" className="ok">{notice}</p> : null}
      <label>{t("correction.parameter")}
        <select name="parameter" required>{PARAMETERS.map((p) => <option key={p} value={p}>{t(`correction.parameters.${p}`)}</option>)}</select>
      </label>
      <div className="form-row">
        <label>{t("correction.current")}<input name="current_value" required maxLength={120} /></label>
        <label>{t("correction.corrected")}<input name="corrected_value" required maxLength={120} /></label>
      </div>
      <label>{t("correction.reason")}<textarea name="reason" required minLength={10} maxLength={1000} /></label>
      <div className="actions"><button type="submit" className="primary">{t("correction.submit")}</button></div>
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </form>
  );
}
