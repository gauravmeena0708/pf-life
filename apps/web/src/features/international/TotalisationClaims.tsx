import { useTranslation } from "react-i18next";
import { useState, type FormEvent } from "react";

import { command, type Envelope } from "../../api/client";
import { ProblemMessage } from "../../components/ProblemMessage";
import { statusLabel } from "../statusLabel";
import { useAgreements } from "./AgreementsTable";

interface Period { from: string; to: string; country: string }
interface Result { reference: string; months_by_country: Record<string, number>; liaison_office: string }
const blank = (country: string): Period => ({ from: "", to: "", country });

export function TotalisationClaims() {
  const { t } = useTranslation(); const agreements = useAgreements();
  const countries = agreements.data?.data.agreements.filter((item) => item.totalisation).map((item) => item.country) ?? [];
  const [country, setCountry] = useState(""); const [periods, setPeriods] = useState<Period[]>([blank("India")]);
  const [result, setResult] = useState<Result | null>(null); const [error, setError] = useState<unknown>(null); const [busy, setBusy] = useState(false);
  const selected = countries.includes(country) ? country : countries[0] ?? "";
  function changePeriod(index: number, field: keyof Period, value: string) {
    setPeriods((old) => old.map((period, i) => i === index ? { ...period, [field]: value } : period));
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (busy || !selected) return;
    const f = new FormData(e.currentTarget); const value = (key: string) => String(f.get(key) ?? "").trim();
    setError(null); setResult(null); setBusy(true);
    try { setResult((await command<Envelope<Result>>("POST", "/api/v1/international/totalisation-claims", {
      direction: value("direction"), country: selected, uan: value("uan"), foreign_insurance_no: value("foreign_insurance_no"),
      benefit: value("benefit"), periods, notes: value("notes"),
    })).data); } catch (cause) { setError(cause); } finally { setBusy(false); }
  }
  return <section className="card stack" aria-labelledby="totalisation-heading"><h2 id="totalisation-heading">Totalisation claims</h2>
    <ProblemMessage error={error ?? agreements.error} />
    {agreements.isLoading ? <p role="status">Loading eligible agreements…</p> : null}
    {agreements.data && !countries.length ? <p className="muted">No totalisation agreements available.</p> : null}
    {countries.length ? <form className="stack" onSubmit={(e) => void submit(e)}><fieldset className="stack" disabled={busy}><legend>Claim details</legend>
      <div className="form-row"><label>Direction<select name="direction">{["INBOUND", "OUTBOUND"].map((code) => <option key={code} value={code}>{statusLabel(code, t)}</option>)}</select></label>
        <label>Agreement country<select name="country" value={selected} onChange={(e) => { setCountry(e.target.value); setPeriods((old) => old.map((period) => countries.includes(period.country) ? { ...period, country: e.target.value } : period)); }}>
          {countries.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
        <label>UAN<input name="uan" required pattern="[0-9]{12}" inputMode="numeric" /></label></div>
      <div className="form-row"><label>Foreign insurance number<input name="foreign_insurance_no" required maxLength={80} /></label>
        <label>Benefit<select name="benefit">{["OLD_AGE", "INVALIDITY", "SURVIVORS"].map((code) => <option key={code} value={code}>{statusLabel(code, t)}</option>)}</select></label></div>
      <fieldset className="stack"><legend>Coverage periods</legend>{periods.map((period, i) => <div className="form-row" key={i}>
        <label>From<input type="date" required value={period.from} onChange={(e) => changePeriod(i, "from", e.target.value)} /></label>
        <label>To<input type="date" required min={period.from || undefined} value={period.to} onChange={(e) => changePeriod(i, "to", e.target.value)} /></label>
        <label>Country<select value={period.country} onChange={(e) => changePeriod(i, "country", e.target.value)}><option value="India">India</option><option value={selected}>{selected}</option></select></label>
        {periods.length > 1 ? <button type="button" onClick={() => setPeriods((old) => old.filter((_, index) => index !== i))}>Remove period</button> : null}
      </div>)}<button type="button" onClick={() => setPeriods((old) => [...old, blank(selected)])}>Add period</button></fieldset>
      <label>Notes<textarea name="notes" maxLength={2000} /></label><div className="actions"><button type="submit" className="primary">Route totalisation claim</button></div>
    </fieldset></form> : null}
    {result ? <div role="status" className="stack"><h3>Reference {result.reference}</h3><p>Liaison office: {result.liaison_office}</p>
      <ul>{Object.entries(result.months_by_country).map(([name, months]) => <li key={name}>{name}: {months} months</li>)}</ul></div> : null}
  </section>;
}
