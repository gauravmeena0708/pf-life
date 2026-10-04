import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

export interface FieldError { field?: string; message: string; onClick?: () => void }

/** P2.28: every problem at the top of the form, each linking to its field; it takes focus so a screen reader hears it. */
export function ErrorSummary({ errors }: { errors: FieldError[] }) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const key = errors.map((e) => e.message).join("|");
  useEffect(() => { if (key) box.current?.focus(); }, [key]);
  if (!errors.length) return null;
  return (
    <div ref={box} className="ui-error-summary" role="alert" tabIndex={-1} aria-labelledby="error-summary-title">
      <h2 id="error-summary-title">{t("ui.thereIsAProblem")}</h2>
      <ul>{errors.map((e) => <li key={e.message}>{e.field ? <a href={`#${e.field}`} onClick={(ev) => {
        ev.preventDefault(); e.onClick?.(); document.getElementById(e.field!)?.focus(); }}>{e.message}</a>
        : e.onClick ? <button type="button" className="link-button" onClick={e.onClick}>{e.message}</button>   // an action, not a place
        : e.message}</li>)}</ul>
    </div>
  );
}
