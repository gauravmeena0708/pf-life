import { useState } from "react";

/** Rupees as the person types them — digits, with or without Indian commas — shown back grouped (1,50,000) when they
 *  leave the field. Whole rupees only. */
export function groupIndian(rupees: number): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(rupees);
}

export function parseRupees(text: string): number | null {
  const plain = text.replace(/[,\s₹]/g, "");
  return /^\d{1,12}$/.test(plain) ? Number(plain) : null;
}

export function MoneyInput({ id, label, hint, error, value, onChange }: {
  id: string; label: string; hint?: string; error?: string; value: number | null; onChange: (rupees: number | null, text: string) => void;
}) {
  const [text, setText] = useState(value === null ? "" : groupIndian(value));
  const described = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`ui-field${error ? " has-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {hint ? <p id={`${id}-hint`} className="ui-hint">{hint}</p> : null}
      {error ? <p id={`${id}-error`} className="ui-field-error"><span className="visually-hidden">Error: </span>{error}</p> : null}
      <div className="ui-money"><span aria-hidden="true">₹</span>
        <input id={id} name={id} inputMode="numeric" autoComplete="off" value={text} aria-invalid={!!error} aria-describedby={described}
          onChange={(e) => { setText(e.target.value); onChange(parseRupees(e.target.value), e.target.value); }}
          onBlur={() => { const n = parseRupees(text); if (n !== null) setText(groupIndian(n)); }} /></div>
    </div>
  );
}
