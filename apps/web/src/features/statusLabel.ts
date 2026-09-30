import type { TFunction } from "i18next";

export function statusLabel(code: string | null | undefined, t: TFunction): string {
  if (!code) return "—";
  const fallback = code.replaceAll("_", " ").toLowerCase();
  return t(`status.${code}`, { defaultValue: t(`journeyB.states.${code}`, { defaultValue: fallback }) });
}
