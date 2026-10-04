import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, command, rupees, type Envelope } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { Stepper } from "../../components/ui/Stepper";
import { ErrorSummary, type FieldError } from "../../components/ui/ErrorSummary";
import { SummaryList, type SummaryRow } from "../../components/ui/SummaryList";
import { ConfirmationPanel } from "../../components/ui/ConfirmationPanel";
import { extractErrors } from "../../components/ui/problems";
import { employmentLabel } from "../../components/ui/format";
import { useStepUp } from "../stepup/useStepUp";
import { StepUpDialog } from "../stepup/StepUpDialog";

interface MemberIdRow {
  account_link_id: string;
  establishment_name: string;
  date_of_joining: string;
  date_of_exit: string | null;
  transferred_to: string | null;
  status: string;
  service_months: number;
  mark_exit_allowed: boolean;
  transfer_status: string;
  primary?: boolean;
}

interface ServiceHistoryData {
  uan: string;
  member_ids: MemberIdRow[];
  primary_member_id?: string | null;
  total_service_months?: number;
}

interface EligibleAccount {
  account_link_id: string;
  balance?: { total_paise: number };
}

interface EligibleTypesData {
  accounts: EligibleAccount[];
}

/** P2.28c: Guided journey for members to move an old PF account into their current one (Form 13). */
export function TransferJourneyPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const stepUp = useStepUp();

  const [step, setStep] = useState<number>(0);
  const [selectedFromId, setSelectedFromId] = useState<string | null>(null);
  const [selectedToId, setSelectedToId] = useState<string | null>(null);
  const [stepErrors, setStepErrors] = useState<FieldError[]>([]);
  const [confirmedCaseId, setConfirmedCaseId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const heading = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    heading.current?.focus();
  }, [step]);

  const historyQuery = useQuery({
    queryKey: ["service-history"],
    queryFn: () => api<Envelope<ServiceHistoryData>>("/api/v1/members/me/service-history"),
    retry: false,
  });

  const eligibilityQuery = useQuery({
    queryKey: ["member-claim-eligibility"],
    queryFn: () =>
      api<Envelope<EligibleTypesData>>("/api/v1/members/me/claims/eligible-types").catch(() => ({
        data: { accounts: [] },
        meta: { correlation_id: "", as_of: "" },
      })),
    retry: false,
  });

  const balanceMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const a of eligibilityQuery.data?.data.accounts ?? []) {
      if (a.balance?.total_paise !== undefined) {
        map.set(a.account_link_id, a.balance.total_paise);
      }
    }
    return map;
  }, [eligibilityQuery.data]);

  const ids = historyQuery.data?.data.member_ids ?? [];
  const from = ids.filter((m) => Boolean(m.date_of_exit) && !m.transferred_to);
  const to = ids.filter((m) => !m.date_of_exit && m.primary !== false);

  useEffect(() => {
    if (!selectedToId && to.length > 0) {
      const preferred = to.find((m) => m.primary) ?? to[0];
      setSelectedToId(preferred.account_link_id);
    }
  }, [to, selectedToId]);

  const stepLabels = [
    t("transferJourney.steps.oldAccount"),
    t("transferJourney.steps.currentAccount"),
    t("transferJourney.steps.checkAnswers"),
  ];

  const serverError = historyQuery.error;
  const initialErrors = serverError ? extractErrors(serverError) : [];
  const activeErrors = stepErrors.length > 0 ? stepErrors : initialErrors;

  function handleContinueStep0() {
    if (!selectedFromId) {
      const firstId = from[0]?.account_link_id;
      setStepErrors([
        {
          field: firstId ? `from-${firstId}` : "from-selection",
          message: t("transferJourney.errors.chooseOldAccount"),
        },
      ]);
      return;
    }
    setStepErrors([]);
    setStep(1);
  }

  function handleContinueStep1() {
    if (!selectedToId) {
      const firstId = to[0]?.account_link_id;
      setStepErrors([
        {
          field: firstId ? `to-${firstId}` : "to-selection",
          message: t("transferJourney.errors.chooseCurrentAccount"),
        },
      ]);
      return;
    }
    setStepErrors([]);
    setStep(2);
  }

  const fromAccount = ids.find((m) => m.account_link_id === selectedFromId);
  const toAccount = ids.find((m) => m.account_link_id === selectedToId);
  const fromBalance = selectedFromId ? balanceMap.get(selectedFromId) : undefined;

  async function handleSubmit() {
    if (!selectedFromId || !selectedToId) {
      return;
    }
    setBusy(true);
    setStepErrors([]);
    try {
      const uan = historyQuery.data?.data.uan ?? "";
      const oldEmployer = fromAccount?.establishment_name ?? "";
      const currentEmployer = toAccount?.establishment_name ?? "";
      const summaryText = t("transferJourney.stepUpSummary", {
        oldEmployer,
        currentEmployer,
      });

      const token = await stepUp.ask({
        action: "submit-transfer",
        resourceId: uan,
        summary: summaryText,
      });

      if (!token) {
        setBusy(false);
        return;
      }

      const body = {
        from_account_link_id: selectedFromId,
        to_account_link_id: selectedToId,
        attesting_employer: "PRESENT",
      };

      const response = await command<Envelope<{ case_id: string }>>(
        "POST",
        "/api/v1/members/me/transfers",
        body,
        { stepUpToken: token }
      );

      await qc.invalidateQueries({ queryKey: ["service-history"] });
      await qc.invalidateQueries({ queryKey: ["applications"] });
      await qc.invalidateQueries({ queryKey: ["member-transfer-legs"] });
      await qc.invalidateQueries({ queryKey: ["member-auto-transfers"] });
      await qc.invalidateQueries({ queryKey: ["member-passbook"] });

      setConfirmedCaseId(response.data.case_id);
    } catch (cause) {
      setStepErrors(extractErrors(cause));
    } finally {
      setBusy(false);
    }
  }

  const fromLabel = fromAccount
    ? employmentLabel(
        fromAccount,
        t("transferJourney.memberId", { id: fromAccount.account_link_id }),
        t("transferJourney.now")
      )
    : "";

  const toLabel = toAccount
    ? employmentLabel(
        toAccount,
        t("transferJourney.memberId", { id: toAccount.account_link_id }),
        t("transferJourney.now")
      )
    : "";

  const summaryRows: SummaryRow[] = [
    {
      key: "from",
      label: t("transferJourney.summary.from"),
      value: fromLabel,
      onChange: () => {
        setStep(0);
        setStepErrors([]);
      },
    },
    {
      key: "into",
      label: t("transferJourney.summary.into"),
      value: toLabel,
      onChange: () => {
        setStep(1);
        setStepErrors([]);
      },
    },
  ];

  if (fromBalance !== undefined) {
    summaryRows.push({
      key: "aboutToMove",
      label: t("transferJourney.summary.aboutToMove"),
      value: t("transferJourney.summary.aboutToMoveValue", { amount: rupees(fromBalance) }),
      onChange: () => {
        setStep(0);
        setStepErrors([]);
      },
    });
  }

  if (confirmedCaseId) {
    return (
      <section className="stack" aria-labelledby="transfer-journey-heading">
        <PageHeader
          id="transfer-journey-heading"
          eyebrow={t("transferJourney.eyebrow")}
          title={t("transferJourney.title")}
          description={t("transferJourney.description")}
          parent={{ label: t("transferJourney.parent"), to: "/member/service" }}
          current={t("transferJourney.current")}
        />
        <ConfirmationPanel
          title={t("transferJourney.confirmation.title")}
          referenceLabel={t("transferJourney.confirmation.referenceLabel")}
          reference={confirmedCaseId}
        >
          <div className="ui-confirmation-body stack">
            <ol className="stack">
              <li>{t("transferJourney.confirmation.step1")}</li>
              <li>{t("transferJourney.confirmation.step2")}</li>
              <li>{t("transferJourney.confirmation.step3")}</li>
            </ol>
            <div className="actions confirmation-actions">
              <Link to="/member/service#transfer-status-heading" className="button">
                {t("transferJourney.confirmation.trackTransfer")}
              </Link>
              <Link to="/member/service" className="button">
                {t("transferJourney.confirmation.backToService")}
              </Link>
            </div>
          </div>
        </ConfirmationPanel>
      </section>
    );
  }

  const isLoading = historyQuery.isLoading;

  return (
    <section className="stack" aria-labelledby="transfer-journey-heading">
      <PageHeader
        id="transfer-journey-heading"
        eyebrow={t("transferJourney.eyebrow")}
        title={t("transferJourney.title")}
        description={t("transferJourney.description")}
        parent={{ label: t("transferJourney.parent"), to: "/member/service" }}
        current={t("transferJourney.current")}
      />

      <Stepper steps={stepLabels} current={step} />

      <div className="card stack">
        <ErrorSummary errors={activeErrors} />

        {isLoading ? <p role="status">{t("transferJourney.loading")}</p> : null}

        {!isLoading && step === 0 ? (
          <div className="journey-step stack" id="from-selection">
            <h2 ref={heading} tabIndex={-1}>{t("transferJourney.step1.heading")}</h2>
            {from.length === 0 ? (
              <div className="stack">
                <p>{t("transferJourney.step1.noneAvailable")}</p>
                {ids.length === 0 ? (
                  <p className="muted">{t("transferJourney.step1.noAccounts")}</p>
                ) : (
                  <ul className="stack">
                    {ids.map((m) => {
                      if (m.transferred_to) {
                        return (
                          <li key={m.account_link_id}>
                            <strong>{m.establishment_name}</strong>: {t("transferJourney.step1.alreadyTransferred", { target: m.transferred_to })}
                          </li>
                        );
                      }
                      if (!m.date_of_exit) {
                        return (
                          <li key={m.account_link_id}>
                            {t("transferJourney.step1.exitNotMarked", { employer: m.establishment_name })}{" "}
                            <Link to="/member/service#exit-heading">
                              {t("transferJourney.step1.markExit")}
                            </Link>
                          </li>
                        );
                      }
                      return null;
                    })}
                  </ul>
                )}
              </div>
            ) : (
              <fieldset className="radio-group stack">
                <legend className="visually-hidden">{t("transferJourney.step1.heading")}</legend>
                {from.map((account) => {
                  const isSelected = selectedFromId === account.account_link_id;
                  const labelText = employmentLabel(
                    account,
                    t("transferJourney.memberId", { id: account.account_link_id }),
                    t("transferJourney.now")
                  );
                  const balancePaise = balanceMap.get(account.account_link_id);
                  const y = Math.floor(account.service_months / 12);
                  const mo = account.service_months % 12;
                  const serviceText = t("transferJourney.serviceDuration", { years: y, months: mo });

                  return (
                    <label
                      key={account.account_link_id}
                      className={`journey-radio-item ${isSelected ? "selected" : ""}`}
                      htmlFor={`from-${account.account_link_id}`}
                    >
                      <input
                        type="radio"
                        id={`from-${account.account_link_id}`}
                        name="from_choice"
                        value={account.account_link_id}
                        checked={isSelected}
                        onChange={() => {
                          setSelectedFromId(account.account_link_id);
                          setStepErrors([]);
                        }}
                      />
                      <div className="journey-radio-content">
                        <div className="radio-title-row">
                          <strong>{labelText}</strong>
                        </div>
                        <span className="muted small">{t("transferJourney.memberId", { id: account.account_link_id })}</span>
                        <span className="small">{serviceText}</span>
                        {balancePaise !== undefined ? (
                          <span className="small">{t("transferJourney.step1.aboutAmount", { amount: rupees(balancePaise) })}</span>
                        ) : null}
                      </div>
                    </label>
                  );
                })}
              </fieldset>
            )}

            <details className="journey-details">
              <summary>{t("transferJourney.step1.whyMoveTitle")}</summary>
              <p>{t("transferJourney.step1.whyMoveBody")}</p>
            </details>

            <div className="actions">
              <button
                type="button"
                className="primary"
                onClick={handleContinueStep0}
                disabled={from.length === 0}
              >
                {t("transferJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 1 ? (
          <div className="journey-step stack" id="to-selection">
            <h2 ref={heading} tabIndex={-1}>{t("transferJourney.step2.heading")}</h2>
            {to.length === 0 ? (
              <p className="muted">{t("transferJourney.step2.noCurrentAccount")}</p>
            ) : (
              <fieldset className="radio-group stack">
                <legend className="visually-hidden">{t("transferJourney.step2.heading")}</legend>
                {to.map((account) => {
                  const isSelected = selectedToId === account.account_link_id;
                  const labelText = employmentLabel(
                    account,
                    t("transferJourney.memberId", { id: account.account_link_id }),
                    t("transferJourney.now")
                  );
                  const y = Math.floor(account.service_months / 12);
                  const mo = account.service_months % 12;
                  const serviceText = t("transferJourney.serviceDuration", { years: y, months: mo });

                  return (
                    <label
                      key={account.account_link_id}
                      className={`journey-radio-item ${isSelected ? "selected" : ""}`}
                      htmlFor={`to-${account.account_link_id}`}
                    >
                      <input
                        type="radio"
                        id={`to-${account.account_link_id}`}
                        name="to_choice"
                        value={account.account_link_id}
                        checked={isSelected}
                        onChange={() => {
                          setSelectedToId(account.account_link_id);
                          setStepErrors([]);
                        }}
                      />
                      <div className="journey-radio-content">
                        <div className="radio-title-row">
                          <strong>{labelText}</strong>
                          {account.primary ? <span className="state-pill">{t("transferJourney.primary")}</span> : null}
                        </div>
                        <span className="muted small">{t("transferJourney.memberId", { id: account.account_link_id })}</span>
                        <span className="small">{serviceText}</span>
                        <span className="muted small">{t("transferJourney.step2.currentAccountNote")}</span>
                      </div>
                    </label>
                  );
                })}
              </fieldset>
            )}

            <div className="actions">
              <button
                type="button"
                className="button"
                onClick={() => {
                  setStep(0);
                  setStepErrors([]);
                }}
              >
                {t("transferJourney.actions.back")}
              </button>
              <button
                type="button"
                className="primary"
                onClick={handleContinueStep1}
                disabled={to.length === 0}
              >
                {t("transferJourney.actions.continue")}
              </button>
            </div>
          </div>
        ) : null}

        {!isLoading && step === 2 ? (
          <div className="journey-step stack" id="check-answers">
            <h2 ref={heading} tabIndex={-1}>{t("transferJourney.step3.heading")}</h2>
            <SummaryList rows={summaryRows} />
            <p className="muted small">{t("transferJourney.step3.note")}</p>
            <div className="actions">
              <button
                type="button"
                className="button"
                onClick={() => {
                  setStep(1);
                  setStepErrors([]);
                }}
              >
                {t("transferJourney.actions.back")}
              </button>
              <button
                type="button"
                className="primary"
                onClick={handleSubmit}
                disabled={busy || !!stepUp.request || !selectedFromId || !selectedToId}
              >
                {t("transferJourney.actions.sendRequest")}
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <StepUpDialog request={stepUp.request} onConfirmed={stepUp.onConfirmed} onCancel={stepUp.onCancel} />
    </section>
  );
}
