import type { TFunction } from "i18next";
import { statusLabel } from "./statusLabel";

export function stateLabel(value: string, t: TFunction): string {
  return statusLabel(value, t);
}

export function dateTime(value: string | null | undefined, language: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(language === "hi" ? "hi-IN" : "en-IN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function dateOnly(value: string | null | undefined, language: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(language === "hi" ? "hi-IN" : "en-IN", { dateStyle: "medium" }).format(date);
}

/** Role IDs contain dots ("fo.ss"), which i18next would read as nested keys, so look them up directly. */
export function roleLabel(role: string, t: TFunction): string {
  const roles = t("journeyB.roles", { returnObjects: true }) as Record<string, string>;
  return typeof roles === "object" && roles[role] ? roles[role] : role;
}
