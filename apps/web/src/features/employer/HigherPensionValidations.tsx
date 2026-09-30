import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, command, rupees, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { HigherPensionDetails, HigherPensionDues, type HigherPensionOption, type HigherPensionPreview } from "../pension/HigherPensionDetails";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

function Validation({ option }: { option: HigherPensionOption }) {
  const qc = useQueryClient();
  const stepUp = useStepUp();
  const [wages, setWages] = useState("");
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<HigherPensionPreview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const disabled = busy || !!stepUp.request;
  const base = `/api/v1/employers/me/higher-pension-options/${encodeURIComponent(option.option_id)}`;

  async function run(decision: "PREVIEW" | "VALIDATE" | "REJECT") {
    if (disabled) return;
    setBusy(true); setError(null); setNotice(null);
    if (decision === "PREVIEW") setPreview(null);
    try {
      if (note.trim().length < 5) throw new Error("Enter a note of at least 5 characters.");
      if (decision !== "REJECT" && !wages.trim()) throw new Error("Enter the monthly wages in rupees.");
      const body = decision === "REJECT" ? { decision: "REJECT", note: note.trim() }
        : { decision: "VALIDATE", wages, note: note.trim() };
      if (decision === "PREVIEW") {
        setPreview((await command<Envelope<HigherPensionPreview>>("POST", `${base}/dues-previews`, body)).data);
        return;
      }
      if (decision === "VALIDATE" && !preview) throw new Error("Preview the dues before validating the option.");
      const token = await stepUp.ask({ action: "validate-higher-pension", resourceId: option.option_id,
        ...(decision === "VALIDATE" ? { amountPaise: preview!.dues_paise } : {}),
        summary: `${decision === "VALIDATE" ? `Validate with dues of ${rupees(preview!.dues_paise)}` : "Reject"} higher-pension option ${option.option_id} for UAN ${option.uan}. ${note.trim()}` });
      if (!token) return;
      await command("POST", `${base}/validations`, body, { stepUpToken: token });
      setNotice(decision === "VALIDATE" ? "Option validated." : "Option rejected."); setPreview(null);
      await qc.invalidateQueries({ queryKey: ["employer-higher-pension"] });
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return <article className="card stack"><h3>{option.name ?? option.uan} · option {option.option_id}</h3>
    <p>Date of joining: {option.date_of_joining ?? "—"}</p><HigherPensionDetails option={option} />
    <ProblemMessage error={error} />{notice ? <p role="status" className="ok">{notice}</p> : null}
    {option.state === "SUBMITTED" ? <form className="stack" aria-label={`Validate higher-pension option ${option.option_id}`}
      onSubmit={(e) => { e.preventDefault(); void run("VALIDATE"); }}>
      <fieldset className="stack" disabled={disabled}><legend>Employer validation</legend>
        <label>Monthly wages (YYYY-MM,rupees per line)<textarea required rows={6} value={wages}
          onChange={(e) => { setWages(e.target.value); setPreview(null); }} /></label>
        <label>Validation note<textarea required minLength={5} maxLength={1000} value={note}
          onChange={(e) => { setNote(e.target.value); setPreview(null); }} /></label>
        {preview ? <div role="status"><HigherPensionDues data={preview} /></div> : null}
        <div className="actions"><button type="button" onClick={() => void run("PREVIEW")}>Preview dues</button>
          <button type="submit" className="primary" disabled={!preview}>Validate</button>
          <button type="button" onClick={() => void run("REJECT")}>Reject</button></div>
      </fieldset>
    </form> : null}
    <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
  </article>;
}

export function HigherPensionValidations() {
  const options = useQuery({ queryKey: ["employer-higher-pension"], retry: false,
    queryFn: () => api<Envelope<HigherPensionOption[]>>("/api/v1/employers/me/higher-pension-options") });
  return <section className="card stack" aria-labelledby="higher-pension-validations-heading">
    <h2 id="higher-pension-validations-heading">Higher-pension joint-option validation</h2>
    <ProblemMessage error={options.error} />
    {options.isLoading ? <p role="status">Loading higher-pension options…</p> : null}
    {options.data?.data.map((option) => <Validation key={option.option_id} option={option} />)}
    {options.data && !options.data.data.length ? <p className="muted">No higher-pension options to review.</p> : null}
  </section>;
}
