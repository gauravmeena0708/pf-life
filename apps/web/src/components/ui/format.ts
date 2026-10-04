/** P2.28: dates the way people in India write them — dd/mm/yyyy. */
export function ddmmyyyy(iso: string | Date | null | undefined): string {
  if (!iso) return "—";
  const d = typeof iso === "string" ? new Date(iso.length === 10 ? `${iso}T00:00:00` : iso) : iso;
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export function addDays(day: Date, n: number): Date {
  const d = new Date(day);
  d.setDate(d.getDate() + n);
  return d;
}

/** A member ID as a person knows it: the employer and the years, not AL-0001. */
export function employmentLabel(e: { establishment_name: string; date_of_joining: string; date_of_exit: string | null } | undefined, fallback: string,
                                now: string): string {
  if (!e) return fallback;
  const year = (iso: string) => ddmmyyyy(iso).slice(6);
  return `${e.establishment_name} · ${year(e.date_of_joining)} – ${e.date_of_exit ? year(e.date_of_exit) : now}`;
}
