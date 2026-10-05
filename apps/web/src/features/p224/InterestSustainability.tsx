import { useState } from "react";
import { api, ApiError, type Envelope, rupees } from "../../api/client";
import en from "../../i18n/p224-sustain.en.json";
import hi from "../../i18n/p224-sustain.hi.json";
import "./interestSustainability.css";

export interface YieldAssumptionItem {
  asset_class: string;
  yield_bp: number;
  label?: string | null;
  illustrative?: boolean;
}

export interface AssetClassItem {
  asset_class: string;
  book_value_paise: number;
  yield_bp: number;
  income_paise: number;
}

export interface SustainabilityResult {
  financial_year: string;
  total_book_value_paise: number;
  income_paise: number;
  sensitivity: {
    minus_50_bp_income_paise: number;
    plus_50_bp_income_paise: number;
  };
  proposed_rate_bp: number;
  liability_paise: number;
  surplus_paise: number;
  verdict: "SUSTAINABLE" | "DEFICIT";
  break_even_rate_bp: number | null;
  current_declared_rate_bp: number;
  current_income_paise: number;
  current_liability_paise: number;
  current_surplus_paise: number;
  current_verdict: string;
  by_asset_class: AssetClassItem[];
  yield_assumptions: YieldAssumptionItem[];
}

export function InterestSustainability() {
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const [year, setYear] = useState("2025-26");
  const [rate, setRate] = useState("825");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SustainabilityResult | null>(null);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  // Editable yield assumptions state
  const [editingClass, setEditingClass] = useState<string | null>(null);
  const [editYieldValue, setEditYieldValue] = useState("");
  const [savingYield, setSavingYield] = useState(false);

  const t = language === "en" ? en : hi;

  async function evaluate() {
    setError("");
    setStatusMessage("");
    setResult(null);
    setLoading(true);
    try {
      const response = await api<Envelope<SustainabilityResult>>(
        "/api/v1/ho/finance/interest-sustainability",
        {
          method: "POST",
          body: JSON.stringify({
            financial_year: year,
            proposed_rate_bp: Number(rate),
          }),
        }
      );
      setResult(response.data);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.problem.status === 422) {
          setError(err.problem.detail || err.problem.title || t.noPositionsError);
        } else {
          setError(err.problem.title || t.error);
        }
      } else {
        setError(t.error);
      }
    } finally {
      setLoading(false);
    }
  }

  async function saveYieldAssumption(assetClass: string) {
    if (!/^\d+$/.test(editYieldValue) || Number(editYieldValue) > 10000) return;
    setSavingYield(true);
    setError("");
    setStatusMessage("");
    try {
      await api<Envelope<YieldAssumptionItem>>(
        `/api/v1/ho/finance/yield-assumptions/${encodeURIComponent(assetClass)}`,
        {
          method: "PUT",
          body: JSON.stringify({
            yield_bp: Number(editYieldValue),
          }),
        }
      );
      setStatusMessage(t.updateYieldSuccess);
      setEditingClass(null);
      // The assumptions change the model income; refresh all figures before showing them.
      if (result) {
        setResult(null);
        try {
          const refreshed = await api<Envelope<SustainabilityResult>>(
            "/api/v1/ho/finance/interest-sustainability",
            { method: "POST", body: JSON.stringify({ financial_year: year, proposed_rate_bp: Number(rate) }) }
          );
          setResult(refreshed.data);
        } catch {
          setError(t.error);
        }
      }
    } catch {
      setError(t.updateYieldError);
    } finally {
      setSavingYield(false);
    }
  }

  return (
    <main className="sustain-container shell-width" aria-labelledby="sustain-page-title">
      <header className="sustain-header">
        <div>
          <h1 id="sustain-page-title">{t.title}</h1>
          <p className="sustain-subtitle">{t.subtitle}</p>
        </div>
        <div className="sustain-lang-control">
          <label htmlFor="sustain-lang-select">{t.language}</label>
          <select
            id="sustain-lang-select"
            value={language}
            onChange={(e) => setLanguage(e.target.value as "en" | "hi")}
          >
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
          </select>
        </div>
      </header>

      {error ? (
        <div className="sustain-alert sustain-alert-error" role="alert">
          {error}
        </div>
      ) : null}

      {statusMessage ? (
        <div className="sustain-alert sustain-alert-success" role="status" aria-live="polite">
          {statusMessage}
        </div>
      ) : null}

      <section className="card sustain-form-card stack" aria-labelledby="sustain-form-heading">
        <h2 id="sustain-form-heading" className="eyebrow">
          {t.evaluate}
        </h2>
        <div className="sustain-form-grid">
          <label htmlFor="sustain-fy">
            {t.fy}
            <input
              id="sustain-fy"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              placeholder="2025-26"
            />
          </label>
          <label htmlFor="sustain-rate">
            {t.proposedRate}
            <input
              id="sustain-rate"
              type="number"
              min="0"
              max="2000"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              placeholder="825"
            />
            <span className="sustain-help-text">
              {t.proposedRateHelp} · {rate ? (Number(rate) / 100).toFixed(2) + "%" : ""}
            </span>
          </label>
          <div>
            <button
              className="primary"
              type="button"
              disabled={loading || !rate || !year}
              onClick={() => void evaluate()}
            >
              {loading ? t.evaluating : t.evaluate}
            </button>
          </div>
        </div>
      </section>

      {result ? (
        <>
          <section className="card stack" aria-labelledby="sustain-results-heading">
            <header className="workspace-head">
              <div>
                <h2 id="sustain-results-heading">{t.resultsHeading}</h2>
                <p>
                  {t.fy}: {result.financial_year} · {t.proposedRate}: {result.proposed_rate_bp} {t.bp} (
                  {(result.proposed_rate_bp / 100).toFixed(2)}%)
                </p>
              </div>
              <div>
                <span
                  className={
                    result.verdict === "SUSTAINABLE"
                      ? "sustain-badge sustain-badge-sustainable"
                      : "sustain-badge sustain-badge-deficit"
                  }
                  data-testid="sustain-verdict-badge"
                >
                  {result.verdict === "SUSTAINABLE" ? t.sustainable : t.deficit}
                </span>
              </div>
            </header>

            <div className="sustain-metrics-grid">
              <article className="sustain-metric-card">
                <div className="sustain-metric-label">{t.income}</div>
                <div className="sustain-metric-value">{rupees(result.income_paise)}</div>
                <div className="sustain-metric-sub">{result.income_paise.toLocaleString("en-IN")} {t.paise}</div>
              </article>

              <article className="sustain-metric-card">
                <div className="sustain-metric-label">{t.liability}</div>
                <div className="sustain-metric-value">{rupees(result.liability_paise)}</div>
                <div className="sustain-metric-sub">{result.liability_paise.toLocaleString("en-IN")} {t.paise}</div>
              </article>

              <article className="sustain-metric-card">
                <div className="sustain-metric-label">
                  {result.surplus_paise >= 0 ? t.surplus : t.deficitAmount}
                </div>
                <div
                  className={`sustain-metric-value ${result.surplus_paise < 0 ? "sustain-negative" : ""}`}
                >
                  {result.surplus_paise < 0 ? "−" : ""}
                  {rupees(Math.abs(result.surplus_paise))}
                </div>
                <div className="sustain-metric-sub">
                  {result.surplus_paise.toLocaleString("en-IN")} {t.paise}
                </div>
              </article>

              <article className="sustain-metric-card">
                <div className="sustain-metric-label">{t.breakEvenRate}</div>
                <div className="sustain-metric-value">
                  {result.break_even_rate_bp === null ? t.unavailable : `${result.break_even_rate_bp} ${t.bp}`}
                </div>
                <div className="sustain-metric-sub">
                  {result.break_even_rate_bp === null ? "" : `${(result.break_even_rate_bp / 100).toFixed(2)}%`}
                </div>
              </article>
            </div>

            <div className="sustain-sensitivity-box">
              <h3 className="sustain-sensitivity-title">{t.sensitivityHeading}</h3>
              <div className="sustain-sensitivity-row">
                <span>{t.incomeMinus50}:</span>
                <strong>{rupees(result.sensitivity.minus_50_bp_income_paise)}</strong>
              </div>
              <div className="sustain-sensitivity-row">
                <span>{t.incomePlus50}:</span>
                <strong>{rupees(result.sensitivity.plus_50_bp_income_paise)}</strong>
              </div>
            </div>

            {result.current_declared_rate_bp ? (
              <div className="card stack sustain-current-card">
                <h3 className="sustain-current-title">
                  {t.currentDeclaredHeading}
                </h3>
                <div className="sustain-metrics-grid">
                  <div>
                    <span className="sustain-metric-label">{t.income}</span>
                    <div>{rupees(result.current_income_paise)}</div>
                  </div>
                  <div>
                    <span className="sustain-metric-label">{t.currentRate}</span>
                    <div>
                      <strong>
                        {result.current_declared_rate_bp} {t.bp} (
                        {(result.current_declared_rate_bp / 100).toFixed(2)}%)
                      </strong>
                    </div>
                  </div>
                  <div>
                    <span className="sustain-metric-label">{t.currentLiability}</span>
                    <div>{rupees(result.current_liability_paise)}</div>
                  </div>
                  <div>
                    <span className="sustain-metric-label">{t.currentSurplus}</span>
                    <div className={result.current_surplus_paise < 0 ? "sustain-negative" : ""}>
                      {result.current_surplus_paise < 0 ? "−" : ""}
                      {rupees(Math.abs(result.current_surplus_paise))}
                    </div>
                  </div>
                  <div>
                    <span className="sustain-metric-label">{t.currentVerdict}</span>
                    <div>
                      <span
                        className={
                          result.current_verdict === "SUSTAINABLE"
                            ? "sustain-badge sustain-badge-sustainable"
                            : "sustain-badge sustain-badge-deficit"
                        }
                      >
                        {result.current_verdict === "SUSTAINABLE" ? t.sustainable : t.deficit}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </section>

          {result.by_asset_class && result.by_asset_class.length > 0 ? (
            <section className="card stack" aria-labelledby="sustain-portfolio-heading">
              <h2 id="sustain-portfolio-heading">{t.byAssetClassHeading}</h2>
              <div className="table-scroll">
                <table>
                  <caption>{t.byAssetClassHeading}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t.assetClass}</th>
                      <th scope="col">{t.bookValue}</th>
                      <th scope="col">{t.yield}</th>
                      <th scope="col">{t.projectedIncome}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.by_asset_class.map((item) => (
                      <tr key={item.asset_class}>
                        <th scope="row">{item.asset_class}</th>
                        <td>{rupees(item.book_value_paise)}</td>
                        <td>
                          {item.yield_bp} {t.bp} ({(item.yield_bp / 100).toFixed(2)}%)
                        </td>
                        <td>{rupees(item.income_paise)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {result.yield_assumptions && result.yield_assumptions.length > 0 ? (
            <section className="card stack" aria-labelledby="sustain-yields-heading">
              <header className="workspace-head">
                <div>
                  <h2 id="sustain-yields-heading">{t.yieldAssumptionsHeading}</h2>
                  <p>{t.yieldAssumptionsNote}</p>
                </div>
              </header>
              <div className="table-scroll">
                <table>
                  <caption>{t.yieldAssumptionsHeading}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t.assetClass}</th>
                      <th scope="col">{t.yield}</th>
                      <th scope="col">{t.action}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.yield_assumptions.map((item) => {
                      const isEditing = editingClass === item.asset_class;
                      return (
                        <tr key={item.asset_class}>
                          <th scope="row">
                            {item.label || item.asset_class}
                            <div className="sustain-help-text">{item.asset_class}</div>
                          </th>
                          <td>
                            {isEditing ? (
                              <div className="sustain-edit-row">
                                <input
                                  type="number"
                                  min="0"
                                  max="10000"
                                  value={editYieldValue}
                                  onChange={(e) => setEditYieldValue(e.target.value)}
                                  style={{ width: "90px" }}
                                  aria-label={`${t.yieldFor} ${item.asset_class}`}
                                />
                                <span>{t.bp}</span>
                              </div>
                            ) : (
                              `${item.yield_bp} ${t.bp} (${(item.yield_bp / 100).toFixed(2)}%)`
                            )}
                          </td>
                          <td>
                            {isEditing ? (
                              <div className="actions">
                                <button
                                  className="primary"
                                  type="button"
                                  disabled={savingYield}
                                  onClick={() => void saveYieldAssumption(item.asset_class)}
                                >
                                  {t.save}
                                </button>
                                <button
                                  className="secondary"
                                  type="button"
                                  disabled={savingYield}
                                  onClick={() => setEditingClass(null)}
                                >
                                  {t.cancel}
                                </button>
                              </div>
                            ) : (
                              <button
                                className="secondary"
                                type="button"
                                onClick={() => {
                                  setEditingClass(item.asset_class);
                                  setEditYieldValue(String(item.yield_bp));
                                }}
                              >
                                {t.edit}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
