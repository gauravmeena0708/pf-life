import { useState } from "react";
import { useTranslation } from "react-i18next";

import { command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";

/** Form 15G / 15H: a self-declaration that no tax is payable this financial year, which waives TDS on withdrawals. */
export function TaxDeclaration() {
  const { t } = useTranslation();
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  return (
    <form className="card stack" aria-labelledby="tax-declaration-heading" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget);
      void (async () => { setError(null); try {
        const r = await command<Envelope<{ form: string; financial_year: string; effect: string }>>("POST", "/api/v1/members/me/tax/form-15g-15h",
          { form: String(f.get("form")), declaration: f.get("declaration") === "on" });
        setDone(`${t("tax.recorded", { form: r.data.form, year: r.data.financial_year })} ${r.data.effect}`);
      } catch (cause) { setError(cause); } })(); }}>
      <h2 id="tax-declaration-heading">{t("tax.title")}</h2>
      <p className="muted small">{t("tax.help")}</p>
      <ProblemMessage error={error} />
      {done ? <p role="status" className="ok">{done}</p> : <>
        <fieldset className="case-options"><legend>{t("tax.form")}</legend>
          <label className="check-row"><input type="radio" name="form" value="15G" required />{t("tax.form15g")}</label>
          <label className="check-row"><input type="radio" name="form" value="15H" />{t("tax.form15h")}</label>
        </fieldset>
        <label className="check-row"><input type="checkbox" name="declaration" required />{t("tax.declare")}</label>
        <div className="actions"><button type="submit">{t("tax.submit")}</button></div>
      </>}
    </form>
  );
}
