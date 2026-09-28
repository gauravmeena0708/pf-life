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

export interface InterestRules { rates_bp: Record<string, number> }

export interface TdsRules {
  applies_to_claim_types: string[];
  threshold_paise: number;
  rate_with_pan_bp: number;
  rate_without_pan_bp: number;
  exempt_after_service_months: number;
  form_15g_15h_waiver: boolean;
}

export interface PensionRules {
  divisor: number;
  salary_months: number;
  pensionable_salary_cap_paise: number;
  min_service_years: number;
  weightage_years: number;
  weightage_after_service_years: number;
  normal_age_years: number;
  earliest_age_years: number;
  early_reduction_bp_per_year: number;
  minimum_pension_paise: number;
  applies_to_pensions_in_payment: boolean;
  revise_in_payment_from: string | null;
}

export interface RuleDocument {
  rule_version: string;
  effective_from: string;
  contribution: Record<string, number>;
  claims: { auto_settlement_limit_paise: number; settlement_sla_days: number; types: Record<string, ClaimType>; approval_bands: Band[] };
  grievances: { categories: string[]; sla_days: { RO: number; ZO: number; HO: number }; reopen_window_days: number };
  interest: InterestRules;
  tds: TdsRules;
  pension: PensionRules;
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
    interest: { financial_year: string; before: string; after: string }[];
    tds: { claim_type: string; amount: string; pan: string; before: string; after: string }[];
    pension: { salary: string; service_years: number; age: number; before: string; after: string }[];
    pensions_in_payment: string;
    note: string;
  } | null;
  decision_note: string | null;
}
