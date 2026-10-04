import type { TFunction } from "i18next";
import type { OfficeCase } from "./types";

export interface TimeLeftResult {
  text: string;
  overdue: boolean;
  dueToday: boolean;
  diffDays: number;
  toString(): string;
}

export type CaseKindCategory = "all" | "claims" | "grievances" | "other";
export type SortOption = "deadline" | "amount" | "oldest";

export interface FilterOptions {
  search?: string;
  kind?: CaseKindCategory;
  overdueOnly?: boolean;
}

export interface QueueCounts {
  overdue: number;
  dueToday: number;
  dueThisWeek: number;
  total: number;
}

function toMidnight(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/**
 * Computes calendar days left until SLA due date.
 * Returns text ("3 days left", "Due today", "Overdue by 2 days") and metadata.
 */
export function timeLeft(
  slaIso: string | null | undefined,
  nowInput: Date | string | number = new Date(),
  t?: TFunction | ((key: string, opts?: Record<string, unknown>) => string)
): TimeLeftResult {
  if (!slaIso) {
    return {
      text: "—",
      overdue: false,
      dueToday: false,
      diffDays: 0,
      toString() {
        return this.text;
      },
    };
  }

  const slaDate = new Date(slaIso);
  if (Number.isNaN(slaDate.getTime())) {
    return {
      text: "—",
      overdue: false,
      dueToday: false,
      diffDays: 0,
      toString() {
        return this.text;
      },
    };
  }

  const nowDate = typeof nowInput === "string" || typeof nowInput === "number" ? new Date(nowInput) : nowInput;
  if (Number.isNaN(nowDate.getTime())) {
    return {
      text: "—",
      overdue: false,
      dueToday: false,
      diffDays: 0,
      toString() {
        return this.text;
      },
    };
  }

  const slaMidnight = toMidnight(slaDate);
  const nowMidnight = toMidnight(nowDate);
  const msPerDay = 86400000;
  const diffDays = Math.round((slaMidnight - nowMidnight) / msPerDay);

  const overdue = diffDays < 0;
  const dueToday = diffDays === 0;

  let text: string;
  if (overdue) {
    const count = Math.abs(diffDays);
    const fallback = count === 1 ? "Overdue by 1 day" : `Overdue by ${count} days`;
    text = t ? t("queueUx.overdueDays", { count, defaultValue: fallback }) : fallback;
  } else if (dueToday) {
    text = t ? t("queueUx.dueToday", { defaultValue: "Due today" }) : "Due today";
  } else {
    const count = diffDays;
    const fallback = count === 1 ? "1 day left" : `${count} days left`;
    text = t ? t("queueUx.daysLeft", { count, defaultValue: fallback }) : fallback;
  }

  return {
    text,
    overdue,
    dueToday,
    diffDays,
    toString() {
      return this.text;
    },
  };
}

/**
 * Classifies an OfficeCase into one of: "claims", "grievances", "other".
 */
export function getCaseCategory(item: OfficeCase): "claims" | "grievances" | "other" {
  if (item.grievance_id || item.kind?.toLowerCase() === "grievance") {
    return "grievances";
  }
  if (item.claim_id || item.kind?.toLowerCase() === "claim" || (item.form_type && !item.process)) {
    return "claims";
  }
  return "other";
}

/**
 * Filters queue items by text search, kind, and overdue status.
 */
export function filterCases(
  items: OfficeCase[],
  filters: FilterOptions,
  nowInput?: Date | string | number
): OfficeCase[] {
  const q = filters.search?.trim().toLowerCase();
  const kind = filters.kind && filters.kind !== "all" ? filters.kind : null;
  const overdueOnly = Boolean(filters.overdueOnly);

  return items.filter((item) => {
    if (q) {
      const matchCase = item.case_id?.toLowerCase().includes(q);
      const matchClaim = item.claim_id?.toLowerCase().includes(q);
      const matchGrievance = item.grievance_id?.toLowerCase().includes(q);
      const matchSubject = item.subject_ref?.toLowerCase().includes(q);
      if (!matchCase && !matchClaim && !matchGrievance && !matchSubject) {
        return false;
      }
    }

    if (kind) {
      if (getCaseCategory(item) !== kind) {
        return false;
      }
    }

    if (overdueOnly) {
      if (!item.sla_due_at) return false;
      const { overdue } = timeLeft(item.sla_due_at, nowInput);
      if (!overdue) {
        return false;
      }
    }

    return true;
  });
}

/**
 * Sorts queue items:
 * - "deadline": deadline soonest first (default). Overdue first, then soonest, no deadline last.
 * - "amount": amount high to low.
 * - "oldest": oldest created_at first (or lowest case_id).
 */
export function sortCases(items: OfficeCase[], sortKey: SortOption = "deadline"): OfficeCase[] {
  const result = [...items];
  result.sort((a, b) => {
    if (sortKey === "amount") {
      const amtA = a.amount_paise ?? 0;
      const amtB = b.amount_paise ?? 0;
      if (amtB !== amtA) {
        return amtB - amtA;
      }
      return a.case_id.localeCompare(b.case_id);
    }

    if (sortKey === "oldest") {
      const caA = (a as { created_at?: string | null }).created_at;
      const caB = (b as { created_at?: string | null }).created_at;
      if (caA && caB) {
        const timeA = new Date(caA).getTime();
        const timeB = new Date(caB).getTime();
        if (timeA !== timeB) return timeA - timeB;
      } else if (caA && !caB) {
        return -1;
      } else if (!caA && caB) {
        return 1;
      }
      return a.case_id.localeCompare(b.case_id);
    }

    // Default: "deadline" (soonest first)
    if (a.sla_due_at && b.sla_due_at) {
      const timeA = new Date(a.sla_due_at).getTime();
      const timeB = new Date(b.sla_due_at).getTime();
      if (timeA !== timeB) return timeA - timeB;
    } else if (a.sla_due_at && !b.sla_due_at) {
      return -1;
    } else if (!a.sla_due_at && b.sla_due_at) {
      return 1;
    }
    return a.case_id.localeCompare(b.case_id);
  });
  return result;
}

/**
 * Computes queue summary metrics (overdue, due today, due this week, total).
 */
export function getQueueCounts(
  items: OfficeCase[],
  nowInput?: Date | string | number
): QueueCounts {
  let overdue = 0;
  let dueToday = 0;
  let dueThisWeek = 0;

  for (const item of items) {
    if (!item.sla_due_at) continue;
    const { overdue: isOverdue, dueToday: isToday, diffDays } = timeLeft(item.sla_due_at, nowInput);
    if (isOverdue) {
      overdue++;
    } else if (isToday) {
      dueToday++;
      dueThisWeek++;
    } else if (diffDays <= 7) {
      dueThisWeek++;
    }
  }

  return {
    overdue,
    dueToday,
    dueThisWeek,
    total: items.length,
  };
}
