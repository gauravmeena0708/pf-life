/** Form fields for rule-set amounts (entered in rupees, stored in paise) and whole numbers. */
export const toPaise = (rupeesText: string): number | null => rupeesText.trim() === "" ? null : Math.round(Number(rupeesText) * 100);
export const toRupees = (paise: number | null | undefined): string => paise === null || paise === undefined ? "" : String(paise / 100);

export function Money({ label, value, onChange, disabled, blank }: { label: string; value: number | null | undefined; onChange: (p: number | null) => void; disabled: boolean; blank?: string }) {
  return <label>{label}<input inputMode="numeric" value={toRupees(value)} disabled={disabled} placeholder={blank}
    onChange={(e) => onChange(toPaise(e.target.value.replace(/[^0-9.]/g, "")))} /></label>;
}

export function Num({ label, value, onChange, disabled, suffix }: { label: string; value: number | null | undefined; onChange: (n: number | null) => void; disabled: boolean; suffix?: string }) {
  return <label>{label}{suffix ? <span className="muted small"> ({suffix})</span> : null}<input inputMode="numeric" value={value ?? ""} disabled={disabled}
    onChange={(e) => onChange(e.target.value.trim() === "" ? null : Number(e.target.value))} /></label>;
}
