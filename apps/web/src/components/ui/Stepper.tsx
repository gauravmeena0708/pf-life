import { useTranslation } from "react-i18next";

/** P2.28: where the person is in a task — "Step 2 of 5", the steps listed, the current one marked for assistive tech. */
export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  const { t } = useTranslation();
  return (
    <nav className="ui-stepper" aria-label={t("ui.progress")}>
      <p className="ui-stepper-count">{t("ui.stepOf", { step: current + 1, total: steps.length })}</p>
      <ol>{steps.map((label, i) => <li key={label} className={i < current ? "done" : i === current ? "current" : undefined}
        aria-current={i === current ? "step" : undefined}><span className="ui-stepper-dot" aria-hidden="true">{i < current ? "✓" : i + 1}</span>{label}</li>)}</ol>
    </nav>
  );
}
