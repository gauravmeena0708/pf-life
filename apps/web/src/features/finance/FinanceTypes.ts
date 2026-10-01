export interface Amounts { book_value_paise: number; market_value_paise: number; unrealised_gain_paise: number }
export interface BalanceSheet { as_of: string; liabilities: { code: string; name: string; amount_paise: number }[]; assets: { code: string; name: string; amount_paise: number }[]; total_liabilities_paise: number; total_assets_paise: number; balanced: boolean; journals_counted: number; note: string }
export interface AssetClass extends Amounts { asset_class: string; share_pct: number; pattern_band: { min_pct: number; max_pct: number }; flag: string }
export interface Investments { as_of: string; funds: { fund: string; asset_classes: AssetClass[]; totals: Amounts }[]; totals: Amounts; fund_managers: string[]; note: string }
export type Meeting = "CBT" | "EC" | "FIAC";
export interface BoardPack { generated_at: string; meeting: Meeting; note: string; sections: {
  contributions: { wage_months: number; returns_filed: number; returns_paid: number; amount_paise: number };
  claims: { received: number; settled: number; rejected: number; average_days_to_settle: number | null; share_settled_within_20_days_pct: number | null };
  grievances: { received: number; resolved: number; pending: number; average_days_to_resolve: number | null };
  investments: { as_of: string; funds: { fund: string; totals: Amounts }[]; totals: Amounts; pattern_flags?: (Pick<AssetClass, "asset_class" | "share_pct" | "pattern_band" | "flag"> & { fund: string })[] };
} }
