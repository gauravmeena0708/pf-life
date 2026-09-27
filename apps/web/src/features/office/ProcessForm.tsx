import { useState, type FormEvent } from "react";

import { command } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { StepUpDialog } from "../stepup/StepUpDialog";
import { useStepUp } from "../stepup/useStepUp";

export interface ProcessOperation {
  process: string; title: string; name: string; method: string; path: string; subject: string;
  step_up: string | null; form: Record<string, { enum?: string[]; min_length?: number }>;
}

const label = (name: string) => name.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

/** One generic form for any tier-2 process operation (ADR-0005): fields, rules and step-up come from the definition. */
export function ProcessForm({ operation, onDone, askSubject = false }: { operation: ProcessOperation; onDone: (msg: string) => void; askSubject?: boolean }) {
  const stepUp = useStepUp();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const form = e.currentTarget;
    const subject = askSubject ? String(f.get("__subject")).trim() : "";
    const path = askSubject ? operation.path.replace(`{${operation.subject}}`, encodeURIComponent(subject)) : operation.path;
    const resourceId = askSubject ? subject : decodeURIComponent(path.split("/").slice(-2)[0]);
    const body = Object.fromEntries(Object.keys(operation.form).map((k) => [k, String(f.get(k) ?? "").trim()]));
    let token: string | null = null;
    if (operation.step_up) {
      token = await stepUp.ask({ action: operation.step_up, resourceId,
        summary: `${label(operation.name)} — ${operation.title} for ${operation.subject.toUpperCase()} ${resourceId}.` });
      if (!token) return;
    }
    setBusy(true); setError(null);
    try {
      await command(operation.method, path, body, { stepUpToken: token ?? undefined });
      form.reset();
      onDone(`${label(operation.name)} recorded.`);
    } catch (cause) { setError(cause); } finally { setBusy(false); }
  }

  return (
    <form className="stack" onSubmit={(e) => void submit(e)}>
      <ProblemMessage error={error} />
      {askSubject ? <label>{operation.subject.toUpperCase()}<input name="__subject" required pattern="[0-9]{12}" inputMode="numeric" /></label> : null}
      {Object.entries(operation.form).map(([name, rule]) => rule.enum ? (
        <fieldset className="case-options" key={name}><legend>{label(name)}</legend>
          {rule.enum.map((v) => <label className="check-row" key={v}><input type="radio" name={name} value={v} required />{label(v.toLowerCase())}</label>)}
        </fieldset>
      ) : (
        <label key={name}>{label(name)}<textarea name={name} required minLength={rule.min_length} /></label>
      ))}
      {operation.step_up ? <p className="muted small">Needs a one-time code bound to this {operation.subject.toUpperCase()}.</p> : null}
      <div className="actions"><button type="submit" className="primary" disabled={busy}>{label(operation.name)}</button></div>
      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </form>
  );
}
