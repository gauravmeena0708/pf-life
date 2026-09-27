export interface Band { upto_paise: number | null; chain: string[] }

export interface ClaimType {
  form_type: string;
  label: string;
  plain_rule: string;
  max_from: "employee_share" | "total_balance";
  max_pct_bp?: number;
  cap_paise?: number | null;
  requires_active_employment?: boolean;
  requires_exit_months?: number | null;
  min_service_months?: number | null;
  once_every_months?: number | null;
  auto_settle_up_to_paise?: number | null;
  approval_bands?: Band[] | null;
  retired?: boolean;
}

export interface RuleDocument {
  rule_version: string;
  effective_from: string;
  contribution: Record<string, number>;
  claims: { auto_settlement_limit_paise: number; settlement_sla_days: number; types: Record<string, ClaimType>; approval_bands: Band[] };
  grievances: { categories: string[]; sla_days: { RO: number; ZO: number; HO: number }; reopen_window_days: number };
  [key: string]: unknown;
}

export interface RuleSetSummary {
  version_id: string; rule_version: string; effective_from: string; status: string; change_note: string;
  base_version_id: string | null; version: number; drafted_by: string; decided_by: string | null; decided_at: string | null;
}

export interface RuleSet extends RuleSetSummary {
  document: RuleDocument;
  checks: string[];
  changes: { path: string; before: unknown; after: unknown }[];
  preview: {
    contribution: { monthly_wages: string; before: Record<string, string>; after: Record<string, string> }[];
    claims: { claim_type: string; amount: string; before: string; after: string }[];
    note: string;
  } | null;
  decision_note: string | null;
}
