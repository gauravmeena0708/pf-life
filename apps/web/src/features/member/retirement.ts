/** P2.23: the retirement view — the PF forecast (contribution-service) and the pension estimate (pension-service) read
 *  together: what each gives a month at 58, the total, and how much of the final wages it replaces. */
export interface PfScenario { vpf_bp: number; corpus_paise: number; employee_paise: number; employer_paise: number; vpf_paise: number;
  interest_paise: number; months: number; final_wages_paise: number; monthly_income_paise: number; vpf_now_monthly_paise: number;
  taxable_interest_years: { financial_year: string; own_contributions_paise: number; above_threshold_paise: number }[] }
export interface PfForecast { as_of: string; retire_on: string; months_to_go: number; balance_now_paise: number; wages_now_paise: number;
  in_service: boolean; scenarios: PfScenario[]; note: string;
  assumptions: { interest_rate_bp: number; interest_declared_for: string | null; wage_growth_bp: number; drawdown_rate_bp: number;
    vpf_max_bp: number; taxable_interest_threshold_paise: number | null; rule_version: string } }
export interface PensionScenario { label: string; service_months: number; eligible: boolean; monthly_paise: number; working?: string; reason?: string }
export interface PensionEstimate { rule_version: string; scenarios: PensionScenario[] }

export interface RetirementRow { vpfPct: number; corpus: number; pfIncome: number; pension: number; total: number;
  replacementPct: number | null; vpfNow: number; taxableYears: number }

/** The pension at 58: staying in service to 58 when the member is in service, else leaving now. */
export function pensionAt58(pf: PfForecast, pension: PensionEstimate | undefined): PensionScenario | undefined {
  return pension?.scenarios[pf.in_service ? 1 : 0] ?? pension?.scenarios[0];
}

export function retirementRows(pf: PfForecast, pension: PensionEstimate | undefined): RetirementRow[] {
  const p = pensionAt58(pf, pension);
  const monthlyPension = p?.eligible ? p.monthly_paise : 0;
  return pf.scenarios.map((s) => {
    const total = s.monthly_income_paise + monthlyPension;
    return { vpfPct: s.vpf_bp / 100, corpus: s.corpus_paise, pfIncome: s.monthly_income_paise, pension: monthlyPension, total,
      replacementPct: s.final_wages_paise > 0 ? Math.round((total * 1000) / s.final_wages_paise) / 10 : null,
      vpfNow: s.vpf_now_monthly_paise, taxableYears: s.taxable_interest_years.length };
  });
}
