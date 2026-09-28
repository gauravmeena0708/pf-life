import { useState } from "react";

import { rupees } from "../../api/client";
import { Money, Num } from "./fields";
import type { InterestRules, PensionRules, RuleSet, TdsRules } from "./types";

const pct = (bp: number | undefined) => bp === undefined ? "" : `${bp / 100}%`;

/** Interest rate declared for each financial year; the annual crediting run uses the version in force. */
export function InterestSection({ value, onChange, disabled }: { value: InterestRules; onChange: (v: InterestRules) => void; disabled: boolean }) {
  const [year, setYear] = useState("");
  const years = Object.keys(value.rates_bp).sort().reverse();
  const setRate = (fy: string, bp: number | null) => onChange({ rates_bp: { ...value.rates_bp, [fy]: bp ?? 0 } });
  return (
    <section className="card stack" aria-labelledby="interest-heading"><h2 id="interest-heading">Interest on PF accounts</h2>
      <p className="muted small">The rate declared for each financial year (illustrative). Finance credits interest once the year has ended,
        on each month&apos;s closing balance. Revising the rate of a year already credited credits (or recovers) only the difference at the next run.</p>
      <div className="table-scroll"><table>
        <thead><tr><th scope="col">Financial year</th><th scope="col">Rate (basis points, 825 = 8.25%)</th><th scope="col">Rate</th><th /></tr></thead>
        <tbody>{years.map((fy) => (
          <tr key={fy}><td>{fy}</td>
            <td><input aria-label={`Interest rate for ${fy} in basis points`} inputMode="numeric" disabled={disabled} value={value.rates_bp[fy]}
              onChange={(e) => setRate(fy, e.target.value.trim() === "" ? null : Number(e.target.value))} /></td>
            <td>{pct(value.rates_bp[fy])}</td>
            <td>{!disabled && years.length > 1 ? <button type="button" onClick={() => {
              const rest = { ...value.rates_bp }; delete rest[fy]; onChange({ rates_bp: rest });
            }}>Remove</button> : null}</td></tr>
        ))}</tbody>
      </table></div>
      {!disabled ? (
        <div className="search-input-row">
          <input aria-label="Financial year to add, like 2026-27" placeholder="2026-27" value={year} onChange={(e) => setYear(e.target.value.replace(/[^0-9-]/g, ""))} />
          <button type="button" disabled={!/^\d{4}-\d{2}$/.test(year) || year in value.rates_bp} onClick={() => { setRate(year, 825); setYear(""); }}>Add financial year</button>
        </div>
      ) : null}
    </section>
  );
}

/** Tax deducted at source on withdrawals, worked out on the payment date. */
export function TdsSection({ value, onChange, claimTypes, disabled }: { value: TdsRules; onChange: (v: TdsRules) => void; claimTypes: string[]; disabled: boolean }) {
  const set = (patch: Partial<TdsRules>) => onChange({ ...value, ...patch });
  return (
    <section className="card stack" aria-labelledby="tds-heading"><h2 id="tds-heading">Tax deducted at source (TDS) on withdrawals</h2>
      <p className="muted small">Applied when the cash section instructs the payment, under the rules in force that day (illustrative, not the Income-tax Act).
        The member receives the amount net of TDS; the tax is held for the tax department.</p>
      <fieldset className="case-options"><legend>Claim types taxed at source</legend>
        {claimTypes.map((code) => <label key={code} className="check-row"><input type="checkbox" disabled={disabled} checked={value.applies_to_claim_types.includes(code)}
          onChange={(e) => set({ applies_to_claim_types: e.target.checked ? [...value.applies_to_claim_types, code] : value.applies_to_claim_types.filter((c) => c !== code) })} />{code}</label>)}
      </fieldset>
      <div className="form-row">
        <Money label="No TDS below (₹)" value={value.threshold_paise} disabled={disabled} onChange={(p) => set({ threshold_paise: p ?? 0 })} />
        <Num label="Rate with a verified PAN" suffix="basis points, 1000 = 10%" value={value.rate_with_pan_bp} disabled={disabled} onChange={(n) => set({ rate_with_pan_bp: n ?? 0 })} />
        <Num label="Rate without a PAN" suffix="basis points" value={value.rate_without_pan_bp} disabled={disabled} onChange={(n) => set({ rate_without_pan_bp: n ?? 0 })} />
      </div>
      <div className="form-row">
        <Num label="No TDS after service of" suffix="months" value={value.exempt_after_service_months} disabled={disabled} onChange={(n) => set({ exempt_after_service_months: n ?? 0 })} />
        <label className="check-row"><input type="checkbox" checked={value.form_15g_15h_waiver} disabled={disabled}
          onChange={(e) => set({ form_15g_15h_waiver: e.target.checked })} />A Form 15G / 15H for the year waives TDS</label>
      </div>
    </section>
  );
}

/** EPS pension formula, and whether a change also revises pensions already in payment. */
export function PensionSection({ value, onChange, effectiveFrom, disabled }: { value: PensionRules; onChange: (v: PensionRules) => void; effectiveFrom: string; disabled: boolean }) {
  const set = (patch: Partial<PensionRules>) => onChange({ ...value, ...patch });
  return (
    <section className="card stack" aria-labelledby="pension-heading"><h2 id="pension-heading">Pension formula (EPS)</h2>
      <p className="muted small">Monthly pension = pensionable salary x pensionable service / divisor, with weightage for long service, a reduction for
        early pension and a minimum (illustrative). Used for new pensions, the members&apos; estimates and the public calculator.</p>
      <div className="form-row">
        <Num label="Divisor" value={value.divisor} disabled={disabled} onChange={(n) => set({ divisor: n ?? 0 })} />
        <Money label="Pensionable salary cap (₹ a month)" value={value.pensionable_salary_cap_paise} disabled={disabled} onChange={(p) => set({ pensionable_salary_cap_paise: p ?? 0 })} />
        <Num label="Salary averaged over" suffix="months" value={value.salary_months} disabled={disabled} onChange={(n) => set({ salary_months: n ?? 0 })} />
      </div>
      <div className="form-row">
        <Num label="Minimum service" suffix="years" value={value.min_service_years} disabled={disabled} onChange={(n) => set({ min_service_years: n ?? 0 })} />
        <Num label="Weightage" suffix="years added" value={value.weightage_years} disabled={disabled} onChange={(n) => set({ weightage_years: n ?? 0 })} />
        <Num label="Weightage after service of" suffix="years" value={value.weightage_after_service_years} disabled={disabled} onChange={(n) => set({ weightage_after_service_years: n ?? 0 })} />
      </div>
      <div className="form-row">
        <Num label="Normal pension age" suffix="years" value={value.normal_age_years} disabled={disabled} onChange={(n) => set({ normal_age_years: n ?? 0 })} />
        <Num label="Earliest pension age" suffix="years" value={value.earliest_age_years} disabled={disabled} onChange={(n) => set({ earliest_age_years: n ?? 0 })} />
        <Num label="Reduction for each year early" suffix="basis points, 400 = 4%" value={value.early_reduction_bp_per_year} disabled={disabled} onChange={(n) => set({ early_reduction_bp_per_year: n ?? 0 })} />
      </div>
      <div className="form-row">
        <Money label="Minimum pension (₹ a month)" value={value.minimum_pension_paise} disabled={disabled} onChange={(p) => set({ minimum_pension_paise: p ?? 0 })} />
      </div>
      <fieldset className="case-options"><legend>Pensions already in payment</legend>
        <label className="check-row"><input type="checkbox" checked={value.applies_to_pensions_in_payment} disabled={disabled}
          onChange={(e) => set({ applies_to_pensions_in_payment: e.target.checked })} />Revise pensions in payment under this formula (never downwards; an APFC (Pension) approves each revision and its arrears)</label>
        {value.applies_to_pensions_in_payment ? (
          <label>Revise with effect from <span className="muted small">(optional; earlier than {effectiveFrom} pays arrears)</span>
            <input type="date" disabled={disabled} max={effectiveFrom} value={value.revise_in_payment_from ?? ""}
              onChange={(e) => set({ revise_in_payment_from: e.target.value || null })} /></label>
        ) : null}
      </fieldset>
    </section>
  );
}

/** Worked examples for interest, TDS and pensions, before and after. */
export function BenefitPreview({ preview }: { preview: NonNullable<RuleSet["preview"]> }) {
  return (
    <>
      <h3>Interest</h3>
      {preview.interest?.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Financial year</th><th scope="col">Rate · on ₹1,00,000 held all year — before</th><th scope="col">After</th></tr></thead>
        <tbody>{preview.interest.map((i) => <tr key={i.financial_year}><td>{i.financial_year}</td><td>{i.before}</td><td><strong>{i.after}</strong></td></tr>)}</tbody>
      </table></div> : <p className="muted">Interest rates are unchanged.</p>}
      <h3>TDS on withdrawals</h3>
      {preview.tds?.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Claim type</th><th scope="col">Withdrawal</th><th scope="col">PAN</th><th scope="col">TDS — before</th><th scope="col">After</th></tr></thead>
        <tbody>{preview.tds.map((t) => <tr key={`${t.claim_type}-${t.amount}-${t.pan}`}><td>{t.claim_type}</td><td>{t.amount}</td><td>{t.pan}</td><td>{t.before}</td><td><strong>{t.after}</strong></td></tr>)}</tbody>
      </table></div> : <p className="muted">TDS is unchanged.</p>}
      <h3>Pensions</h3>
      {preview.pension?.length ? <div className="table-scroll"><table><thead><tr><th scope="col">Pensionable salary</th><th scope="col">Service</th><th scope="col">Age</th><th scope="col">Monthly pension — before</th><th scope="col">After</th></tr></thead>
        <tbody>{preview.pension.map((p) => <tr key={`${p.salary}-${p.service_years}-${p.age}`}><td>{p.salary}</td><td>{p.service_years} years</td><td>{p.age}</td><td>{p.before}</td><td><strong>{p.after}</strong></td></tr>)}</tbody>
      </table></div> : <p className="muted">Pensions are unchanged.</p>}
      {preview.pensions_in_payment ? <p className="demo-tip"><strong>Pensions in payment:</strong> {preview.pensions_in_payment}.</p> : null}
      <p className="muted small">Sample amounts: {rupees(10000000)} balance for interest; withdrawals after 3 years of service for TDS.</p>
    </>
  );
}
