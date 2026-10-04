import { useTranslation } from "react-i18next";

export interface SummaryRow { key: string; label: string; value: React.ReactNode; onChange?: () => void }

/** P2.28: "Check your answers" — each answer with a way back to change it. */
export function SummaryList({ rows }: { rows: SummaryRow[] }) {
  const { t } = useTranslation();
  return (
    <dl className="ui-summary">{rows.map((r) => <div key={r.key} className="ui-summary-row">
      <dt>{r.label}</dt><dd>{r.value}</dd>
      <dd className="ui-summary-action">{r.onChange ? <button type="button" className="link-button" onClick={r.onChange}>
        {t("ui.change")}<span className="visually-hidden"> {r.label}</span></button> : null}</dd>
    </div>)}</dl>
  );
}
