import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { ProblemMessage } from "../../components/ProblemMessage";
import { ConfirmationPanel } from "../../components/ui/ConfirmationPanel";
import { ErrorSummary, type FieldError } from "../../components/ui/ErrorSummary";
import { ddmmyyyy } from "../../components/ui/format";
import { extractErrors } from "../../components/ui/problems";

export interface PayRunSummary {
  pay_run_id: string;
  wage_month: string;
  run_ref: string;
  pay_date: string;
  state: string;
  totals?: {
    gross_paise: number;
    epf_wages_paise: number;
    rows: number;
  };
  rows?: number;
  filing_id?: string | null;
}

export interface MemberMonthTotal {
  uan: string;
  name: string;
  runs: number;
  gross_paise: number;
  epf_wages_paise: number;
  eps_wages_paise: number;
  edli_wages_paise: number;
  ncp_days: number;
}

export interface PayRunsResponse {
  wage_month: string;
  runs: PayRunSummary[];
  members: MemberMonthTotal[];
  can_make_ecr: boolean;
  reason?: string;
}

interface Establishment {
  your_permissions: string[];
}

interface DraftEcrResponse {
  filing?: {
    filing_id: string;
    wage_month?: string;
    state?: string;
  };
  filing_id?: string;
  state?: string;
  validation_report?: {
    valid?: boolean;
    summary?: unknown;
    issues?: unknown[];
  } | string | null;
}

export function PayRunsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const wageMonth = searchParams.get("month") || "2026-08";

  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [draftResult, setDraftResult] = useState<{
    filingId: string;
    validationState: string;
  } | null>(null);

  const establishmentQuery = useQuery({
    queryKey: ["employer-me"],
    queryFn: () => api<Envelope<Establishment>>("/api/v1/employers/me"),
    retry: false,
  });

  const grants = establishmentQuery.data?.data.your_permissions ?? [];
  const canPrepare = grants.includes("ecr.prepare");

  const payRunsQuery = useQuery({
    queryKey: ["pay-runs", wageMonth],
    queryFn: () =>
      api<Envelope<PayRunsResponse>>(
        `/api/v1/employers/me/pay-runs?wage_month=${encodeURIComponent(wageMonth)}`
      ),
    retry: false,
  });

  const runs = payRunsQuery.data?.data?.runs ?? [];
  const members = payRunsQuery.data?.data?.members ?? [];
  const canMakeEcr = payRunsQuery.data?.data?.can_make_ecr ?? false;
  const cannotMakeReason = payRunsQuery.data?.data?.reason;

  const totalRuns = runs.length;
  const runsGrossPaise = runs.reduce((acc, r) => acc + (r.totals?.gross_paise ?? 0), 0);
  const membersGrossPaise = members.reduce((acc, m) => acc + m.gross_paise, 0);
  const totalGrossPaise = runsGrossPaise || membersGrossPaise;

  const runsEpfPaise = runs.reduce((acc, r) => acc + (r.totals?.epf_wages_paise ?? 0), 0);
  const membersEpfPaise = members.reduce((acc, m) => acc + m.epf_wages_paise, 0);
  const totalEpfPaise = runsEpfPaise || membersEpfPaise;

  const totalMembers = members.length;

  async function handleMakeEcr() {
    setErrors([]);
    setBusy(true);

    try {
      const res = await command<Envelope<DraftEcrResponse>>(
        "POST",
        `/api/v1/employers/me/pay-runs/${encodeURIComponent(wageMonth)}/ecr-drafts`
      );

      const filingId = res.data.filing?.filing_id || res.data.filing_id || "";
      const validationState = res.data.filing?.state || res.data.state || "VALIDATED";

      setDraftResult({ filingId, validationState });
      await qc.invalidateQueries({ queryKey: ["pay-runs", wageMonth] });
      await qc.invalidateQueries({ queryKey: ["ecr-filings"] });
    } catch (cause) {
      setErrors(extractErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  function handleMonthChange(newMonth: string) {
    setDraftResult(null);
    setErrors([]);
    setSearchParams({ month: newMonth });
  }

  return (
    <section className="stack" aria-labelledby="pay-runs-heading">
      <PageHeader
        id="pay-runs-heading"
        eyebrow={t("payroll.payRunsEyebrow")}
        title={t("payroll.payRunsTitle")}
        description={t("payroll.payRunsDescription")}
        parent={{ label: "Employer", to: "/employer" }}
        current={t("payroll.payRunsTitle")}
      />

      <ErrorSummary errors={errors} />
      <ProblemMessage error={payRunsQuery.error} />

      {draftResult ? (
        <ConfirmationPanel
          title={t("payroll.ecrDraftCreated")}
          referenceLabel={t("payroll.filingReference")}
          reference={draftResult.filingId}
        >
          <div className="ui-confirmation-body stack">
            <p>
              {t("payroll.validationState")}:{" "}
              <strong>{draftResult.validationState}</strong>
            </p>
            <div className="actions confirmation-actions">
              <Link to="/employer/ecr" className="button primary">
                {t("payroll.goToEcr")}
              </Link>
            </div>
          </div>
        </ConfirmationPanel>
      ) : null}

      <div className="card pay-runs-toolbar">
        <label htmlFor="wage-month-select" className="bold">
          {t("payroll.wageMonth")}:
        </label>
        <input
          id="wage-month-select"
          type="text"
          placeholder="YYYY-MM"
          value={wageMonth}
          onChange={(e) => handleMonthChange(e.target.value)}
        />
      </div>

      <section className="card stack" aria-labelledby="monthly-summary-heading">
        <div className="section-heading">
          <div>
            <h2 id="monthly-summary-heading">{t("payroll.summaryHeading")}</h2>
          </div>
        </div>

        <div className="payroll-metrics-grid">
          <div className="payroll-metric-card">
            <p className="payroll-metric-label">{t("payroll.totalPayRuns")}</p>
            <p className="payroll-metric-value">{totalRuns}</p>
          </div>
          <div className="payroll-metric-card">
            <p className="payroll-metric-label">{t("payroll.totalMembers")}</p>
            <p className="payroll-metric-value">{totalMembers}</p>
          </div>
          <div className="payroll-metric-card">
            <p className="payroll-metric-label">{t("payroll.totalGrossWages")}</p>
            <p className="payroll-metric-value">{rupees(totalGrossPaise)}</p>
          </div>
          <div className="payroll-metric-card">
            <p className="payroll-metric-label">{t("payroll.totalEpfWages")}</p>
            <p className="payroll-metric-value">{rupees(totalEpfPaise)}</p>
          </div>
        </div>

        {!draftResult ? (
          <div className="pay-runs-action-section">
            {canMakeEcr ? (
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={busy || !canPrepare}
                  onClick={() => void handleMakeEcr()}
                >
                  {busy ? t("payroll.makingEcr") : t("payroll.makeEcr")}
                </button>
                {!canPrepare ? (
                  <p className="muted small">{t("payroll.permissionRequired")}</p>
                ) : null}
              </div>
            ) : (
              <div className="ineligible-reasons" role="status">
                <p>{cannotMakeReason || t("payroll.cannotMakeEcr")}</p>
              </div>
            )}
          </div>
        ) : null}
      </section>

      <section className="card stack" aria-labelledby="runs-list-heading">
        <div className="section-heading">
          <div>
            <h2 id="runs-list-heading">
              {t("payroll.runsHeading", { month: wageMonth })}
            </h2>
          </div>
        </div>

        {payRunsQuery.isLoading ? (
          <p className="muted" role="status">Loading...</p>
        ) : null}

        {!payRunsQuery.isLoading && runs.length === 0 ? (
          <p className="muted">{t("payroll.noPayRuns")}</p>
        ) : null}

        {runs.length > 0 ? (
          <div className="table-scroll">
            <table className="responsive-table">
              <thead>
                <tr>
                  <th scope="col">{t("payroll.payDate")}</th>
                  <th scope="col">{t("payroll.runRef")}</th>
                  <th scope="col" className="numeric">{t("payroll.rows")}</th>
                  <th scope="col" className="numeric">{t("payroll.grossWages")}</th>
                  <th scope="col" className="numeric">{t("payroll.epfWages")}</th>
                  <th scope="col">{t("payroll.runState")}</th>
                  <th scope="col">{t("payroll.filingId")}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.pay_run_id}>
                    <td data-label={t("payroll.payDate")}>
                      {ddmmyyyy(run.pay_date)}
                    </td>
                    <td data-label={t("payroll.runRef")}>
                      <code>{run.run_ref}</code>
                    </td>
                    <td data-label={t("payroll.rows")} className="numeric">
                      {run.totals?.rows ?? run.rows ?? 0}
                    </td>
                    <td data-label={t("payroll.grossWages")} className="numeric">
                      {rupees(run.totals?.gross_paise)}
                    </td>
                    <td data-label={t("payroll.epfWages")} className="numeric">
                      {rupees(run.totals?.epf_wages_paise)}
                    </td>
                    <td data-label={t("payroll.runState")}>
                      <span className="state-pill">{run.state}</span>
                    </td>
                    <td data-label={t("payroll.filingId")}>
                      {run.filing_id ? <code>{run.filing_id}</code> : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="card stack" aria-labelledby="members-month-totals-heading">
        <div className="section-heading">
          <div>
            <h2 id="members-month-totals-heading">{t("payroll.membersHeading")}</h2>
          </div>
        </div>

        {payRunsQuery.isLoading ? (
          <p className="muted" role="status">Loading...</p>
        ) : null}

        {!payRunsQuery.isLoading && members.length === 0 ? (
          <p className="muted">{t("payroll.noMembers")}</p>
        ) : null}

        {members.length > 0 ? (
          <div className="table-scroll">
            <table className="responsive-table">
              <thead>
                <tr>
                  <th scope="col">{t("payroll.uan")}</th>
                  <th scope="col">{t("payroll.memberName")}</th>
                  <th scope="col" className="numeric">{t("payroll.payRunsCount")}</th>
                  <th scope="col" className="numeric">{t("payroll.grossWages")}</th>
                  <th scope="col" className="numeric">{t("payroll.epfWages")}</th>
                  <th scope="col" className="numeric">{t("payroll.epsWages")}</th>
                  <th scope="col" className="numeric">{t("payroll.edliWages")}</th>
                  <th scope="col" className="numeric">{t("payroll.ncpDays")}</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.uan}>
                    <td data-label={t("payroll.uan")}>
                      <code>{member.uan}</code>
                    </td>
                    <td data-label={t("payroll.memberName")}>
                      {member.name}
                    </td>
                    <td data-label={t("payroll.payRunsCount")} className="numeric">
                      {member.runs}
                    </td>
                    <td data-label={t("payroll.grossWages")} className="numeric">
                      {rupees(member.gross_paise)}
                    </td>
                    <td data-label={t("payroll.epfWages")} className="numeric">
                      {rupees(member.epf_wages_paise)}
                    </td>
                    <td data-label={t("payroll.epsWages")} className="numeric">
                      {rupees(member.eps_wages_paise)}
                    </td>
                    <td data-label={t("payroll.edliWages")} className="numeric">
                      {rupees(member.edli_wages_paise)}
                    </td>
                    <td data-label={t("payroll.ncpDays")} className="numeric">
                      {member.ncp_days}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </section>
  );
}
